# Analyze your Google Scholar ![https://scholar.google.com/favicon.ico](https://scholar.google.com/favicon.ico)
> Get **insights into your Google Scholar profile**: Which affiliations cite you most? Which are the most cited authors referencing your work?
>
> See[`main.ipynb`](https://nbviewer.org/github/juliusberner/scholar_scraper/blob/main/main.ipynb) for examples. Built with `serpapi` and `folium`.

<p align="center"><img src="assets/citation_map.png" width="95%"></p>

## Usage

1. Register for SerpApi at [https://serpapi.com](https://serpapi.com/). You can start with the free plan. However, depending on the number of your citations, you might need to purchase a paid plan.
2. Clone the repo, create an environment, install the package, and start the jupyter server: 
    ```
    git clone git@github.com:juliusberner/scholar_scraper.git
    cd scholar_scraper
    conda create -n scholar_scraper python==3.9 pip --yes
    conda activate scholar_scraper
    pip install -e .
    jupyter notebook
    ```
3. Run the jupyter notebook [`main.ipynb`](main.ipynb) and visualize your results.
4. *optional:* extend [`assets/affiliations.csv`](assets/affiliations.csv) (current version is based on [https://github.com/endSly/world-universities-csv](https://github.com/endSly/world-universities-csv)) 