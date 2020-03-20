import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="books_info-bsodhi",
    version="0.0.2",
    author="Balwinder Sodhi",
    author_email="flipbrain.in@gmail.com",
    description="Books data scraper.",
    long_description="Scrapes books and articles informatio from Goodreads and Google Scholar",
    long_description_content_type="text/markdown",
    url="https://github.com/bsodhi/books_scraper",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=["requests",
                      "cryptography",
                      "pyOpenSSL",
                      "lxml",
                      "argparse",
                      "beautifulsoup4",
                      "fake_useragent",
                      "scholarly",
                      "selenium", ],
    entry_points={
        'console_scripts': [
            'bscrape=books_scraper.scraper:main',
        ],
    },
)
