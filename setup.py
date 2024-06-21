from setuptools import find_packages, setup

setup(
    name="scholar_scraper",
    version="0.1.0",
    python_requires=">=3.9",
    zip_safe=True,
    packages=find_packages(include=["scholar_scraper"]),
    author="Julius Berner",
    author_email="mail@jberner.info",
    description="Analyze your Google Scholar",
    install_requires=[
        "tldextract==5.1.2",
        "tqdm==4.64.0",
        "pandas==2.2.2",
        "geopy==2.4.1",
        "jupyter==1.0.0",
        "folium==0.17.0",
        "beautifulsoup4==4.11.1",
        "google_search_results==2.4.1",
        "pycountry==24.6.1",
    ],
    extras_require={
        "dev": ["isort==5.10.1", "black==22.10.0"],
    },
)
