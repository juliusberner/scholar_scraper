import contextlib
import logging
import math
import os
import warnings
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import folium
import pandas as pd
import pycountry
import requests
import tldextract
import yaml
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from serpapi import GoogleSearch
from tqdm import TqdmExperimentalWarning

warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)
from tqdm.autonotebook import tqdm

logging.basicConfig(
    filename="log.txt",
    filemode="a",
    format="%(asctime)s | %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


MAX_LEN = 30


def save_yaml(dictionary, path):
    path = Path(path)
    path.parent.mkdir(exist_ok=True, parents=True)
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.dump(dictionary, f, sort_keys=False)
    logger.debug("Saved %s.", path)


def load_yaml(path):
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    logger.debug("Loaded %s.", path)
    return data


def extract_tld(url):
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}"


def extract_mail_domain(mail):
    return extract_tld(mail.split("at ")[-1])


def search(params, key=None, paginate=True, out_path=None, overwrite=False):
    output = []

    # load existing results
    if not overwrite and out_path is not None:
        if paginate:
            files = list(out_path.glob(f"{key}_[0-9]*-[0-9]*.yaml"))
            if len(files) > 0:
                for file in files:
                    output += load_yaml(file)[key]
                return output
        elif out_path.is_file():
            return load_yaml(out_path)

    # defaults
    if "api_key" not in params:
        params["api_key"] = os.environ["SERP_API_KEY"]
    if "num" not in params:
        params["num"] = 20

    # paginate search
    gsearch = GoogleSearch(params)
    while True:
        with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
            results = gsearch.get_dict()
        if results.get("error") is not None:
            raise RuntimeError(results["error"])

        # extract
        if key is None:
            assert not paginate
            output = results
        else:
            new_output = results[key]
            output += new_output

        # save
        if out_path is not None:
            if paginate:
                name = f"{key}_{len(output)-len(new_output)}-{len(output)}.yaml"
                save_yaml(
                    results,
                    out_path / name,
                )
            else:
                save_yaml(results, out_path)

        # stop
        if paginate and "next" in results.get("serpapi_pagination", []):
            gsearch.params_dict.update(
                dict(
                    parse_qsl(
                        urlsplit(results.get("serpapi_pagination").get("next")).query
                    )
                )
            )
        else:
            break

    return output


def scrape_author(author_id, out_path="results", overwrite=False):
    out_path = Path(out_path) / author_id
    params = {
        "engine": "google_scholar_author",
        "author_id": author_id,
        "sort": "pubdate",
    }
    articles = search(
        params, key="articles", paginate=True, out_path=out_path, overwrite=overwrite
    )
    logging.info("Num. of articles: %d", len(articles))

    for article in tqdm(articles, desc="Articles"):
        num_citations = article["cited_by"]["value"]
        logging.info(
            "-- Article: %s | Num. of citations: %s", article["title"], num_citations
        )
        article_path = (
            out_path
            / f"{article['title'][:MAX_LEN]} ({article['citation_id'].split(':')[-1]})"
        )
        result_path = article_path / "results.yaml"

        if num_citations:
            cites_id = article["cited_by"]["cites_id"]
            citations = get_citations(
                cites_id, out_path=article_path, overwrite=overwrite
            )
            if not len(citations) == num_citations:
                logger.warning(
                    "Num of citation missmatch: %s and %s",
                    len(citations),
                    num_citations,
                )
        else:
            citations = []
        article["citations"] = citations
        save_yaml(article, result_path)

    save_yaml(articles, out_path / "results.yaml")
    return articles


def parse_authors(url, out_path=None, overwrite=False):
    if (out_path.parent / "authors.yaml").is_file():
        (out_path.parent / "authors.yaml").unlink()

    # load existing results
    if not overwrite and out_path is not None and out_path.is_file():
        with out_path.open("rb") as f:
            content = f.read()
    # open url
    else:
        content = requests.get(url, timeout=60).content
        if out_path:
            with out_path.open("wb+") as f:
                f.write(content)

    soup = BeautifulSoup(content, "html.parser")

    # find title information
    article = soup.find("div", {"class": "gs_ri"})
    title_elem = article.find("h3", {"class": "gs_rt"})
    title = title_elem.get_text()

    # find author information
    author_info = article.find("div", {"class": "gs_fmaa"})
    # structure changes if multiple references are found
    if author_info is None:
        author_info = article.find("div", {"class": "gs_a"})
        author_names = author_info.get_text().split("- ")[0]
    else:
        author_names = author_info.get_text()

    authors = [
        {"name": name.replace("…", "").strip()} for name in author_names.split(", ")
    ]
    linked_authors = {
        author.get_text(): author["href"] for author in author_info.select("a")
    }
    scholar_url = "https://scholar.google.com"

    for author in authors:
        if author["name"] in linked_authors:
            href = linked_authors[author["name"]]
            author.update({"link": scholar_url + href, "author_id": href[16:28]})

    return title, authors


def get_citations(cites_id, out_path=None, overwrite=False):
    params = {
        "engine": "google_scholar",
        "sort": "pubdate",
        "cites": cites_id,
    }
    citations = search(
        params,
        key="organic_results",
        paginate=True,
        out_path=out_path,
        overwrite=overwrite,
    )

    for citation in citations:
        # get further authors (this is still limited to a max. number)
        # (serp only scrapes the author preview which is limited to the first few authors)
        partial_authors = [
            author["name"] for author in citation["publication_info"].get("authors", [])
        ]
        params = {
            "q": citation["title"] + " " + " ".join(partial_authors),
            "engine": "google_scholar",
            "sort": "pubdate",
        }
        citation_path = (
            out_path / f"{citation['title'][:MAX_LEN]} ({citation['result_id']})"
        )

        results = search(
            params,
            paginate=False,
            out_path=citation_path / "article.yaml",
            overwrite=overwrite,
        )
        url = results["search_metadata"]["raw_html_file"]
        title, authors = parse_authors(
            url, out_path=citation_path / "article.html", overwrite=overwrite
        )

        # check
        citation["warnings"] = []
        if not citation["title"].replace("…", "").strip().lower() in title.lower():
            citation["warnings"].append(
                f"Title missmatch: `{citation['title']}` and `{title}`"
            )
        if not set([a.lower() for a in partial_authors]) <= set(
            a["name"].lower() for a in authors
        ):
            citation["warnings"].append(
                f"Author missmatch: {partial_authors} and {[a['name'] for a in authors]}"
            )
        for warning in citation["warnings"]:
            logger.warning(warning)

        # add authors
        logging.info(
            "---- Citation: %s | Num. of authors: %d", citation["title"], len(authors)
        )
        for author in authors:
            if "author_id" in author:
                params = {
                    "engine": "google_scholar_author",
                    "author_id": author["author_id"],
                }
                author_path = citation_path / f"{author['author_id']}.yaml"
                results = search(
                    params, paginate=False, out_path=author_path, overwrite=overwrite
                )
                author["author"] = results["author"]
                author["cited_by"] = results.get("cited_by", 0)

        # add all author information
        citation["publication_info"]["authors"] = authors

    return citations


def get_country_name(abbrv_name):
    try:
        country = pycountry.countries.get(alpha_2=abbrv_name)
        return country.name
    except LookupError:
        pass


def get_citation_df(results, keep_warnings=False, affil_file="assets/affiliations.csv"):
    # get affiliations df
    affil_df = pd.read_csv(affil_file)
    for col in ["domain", "alt_domain"]:
        rows = ~affil_df.loc[:, col].isna()
        affil_df.loc[rows, col] = affil_df.loc[rows, col].apply(extract_tld)
        # fallback since serl omits dashes in scraped email domains
        affil_df.loc[rows, f"fallback_{col}"] = affil_df.loc[rows, col].apply(
            lambda s: s.replace("-", "")
        )

    # loop through articles, citations, and authors
    df = []
    for article in results:
        for citation in article.get("citations", []):
            if not citation.get("warnings") or keep_warnings:
                for author in citation["publication_info"]["authors"]:
                    author_data = {}
                    # detailed gscholar info
                    if "author" in author:
                        keys = ["name", "affiliations", "email", "website"]
                        author_data.update(
                            {k: v for k, v in author["author"].items() if k in keys}
                        )
                        if "email" in author_data:
                            mail_domain = extract_mail_domain(author_data["email"])
                            author_data["email_domain"] = mail_domain

                            # match affiliations
                            affil = affil_df.loc[
                                (affil_df.loc[:, "domain"] == mail_domain)
                                | (affil_df.loc[:, "alt_domain"] == mail_domain)
                            ]
                            author_data["warnings"] = []
                            if len(affil) == 0:
                                affil = affil_df.loc[
                                    (affil_df.loc[:, "fallback_domain"] == mail_domain)
                                    | (
                                        affil_df.loc[:, "fallback_alt_domain"]
                                        == mail_domain
                                    )
                                ]
                                if len(affil) > 1:
                                    author_data["warnings"].append(
                                        f"Found affiliation without a dash: {mail_domain}"
                                    )
                            if len(affil) > 0:
                                if len(affil) > 1:
                                    author_data["warnings"].append(
                                        f"Found multiple affiliations: {mail_domain}"
                                    )
                                affil_data = (
                                    affil.loc[:, ["affil_country", "affil_name"]]
                                    .iloc[0]
                                    .to_dict()
                                )
                                if not author_data["warnings"] or keep_warnings:
                                    author_data.update(affil_data)

                            for warning in author_data["warnings"]:
                                logger.warning(warning)

                    # citation info
                    if "cited_by" in author:
                        citations = author["cited_by"]
                        if citations:
                            author_data["citations"] = author["cited_by"]["table"][0][
                                "citations"
                            ]["all"]
                        else:
                            author_data["citations"] = 0

                    # cited article
                    cites_id = citation["inline_links"].get("cites_id")
                    if not cites_id and "cited_by" in citation["inline_links"]:
                        cites_id = citation["inline_links"]["cited_by"]["cites_id"]
                    author_data.update(
                        {
                            "abbrv_name": author["name"],
                            "article": article["title"],
                            "article_id": article["citation_id"],
                            "citation": citation["title"],
                            "citation_id": cites_id,
                        }
                    )
                    if "author_id" in author:
                        author_data["author_id"] = author["author_id"]

                    df.append(author_data)

    df = pd.DataFrame.from_dict(df)
    df.loc[df.loc[:, "name"].isna(), "name"] = df.loc[
        df.loc[:, "name"].isna(), "abbrv_name"
    ]
    df.loc[:, "affil_country_name"] = df.loc[:, "affil_country"].apply(get_country_name)
    return df


def drop_and_count_duplicates(df, cols, col_name="count", col_idx=1):
    counts = df.loc[:, cols].groupby(by=cols).transform("size")
    out_df = df.copy()
    out_df.insert(col_idx, col_name, counts)
    return out_df.drop_duplicates(cols)


def get_map(df, out_path=None, overwrite=False, radius_scale=6, radius_log_base=2):
    # load existing results
    countries_path = None if out_path is None else out_path / "countries.yaml"
    if not overwrite and countries_path is not None and countries_path.is_file():
        data = load_yaml(countries_path)

    else:
        geolocator = Nominatim(user_agent="geolocator")
        # extract country locations
        counts = df.loc[:, "affil_country"].value_counts().to_dict()
        data = {}
        for country, count in tqdm(counts.items()):
            loc = geolocator.geocode(country)
            data[country] = {
                "count": count,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
            }
        if countries_path is not None:
            save_yaml(data, countries_path)

    # plot
    world_map = folium.Map(tiles="CartoDB Positron")
    for country, specs in data.items():
        count = specs["count"]
        folium.CircleMarker(
            location=[specs["latitude"], specs["longitude"]],
            tooltip=f"<b>{country}</b>: {count}",
            radius=(math.log(count, radius_log_base) if radius_log_base else count)
            * radius_scale,
            fill=True,
            weight=1.5,
            opacity=0.5,
            fillOpacity=0.2,
        ).add_to(world_map)

    world_map.save(out_path / "map.html")
    return world_map
