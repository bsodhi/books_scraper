# books_scraper
Books scraper for Google Scholar and Goodreads

## Prerequisites
This program makes use of [Selenium WebDriver](https://www.selenium.dev/documentation/en/webdriver/driver_requirements/)
for fetching GoodReads book shelf data. You should have a driver installed for your
browser. Currently supported browsers are: Chrome, Firefox, Edge and Safari. We have tested with Firefox and Safari (on macOSX 10.14.6).

## How to install and run
1. Open a shell
2. `cd some_folder_where_you_want_this_code`
3. `git clone https://github.com/bsodhi/books_scraper.git`
4. `cd books_scraper`
5. `python3 -m venv give_some_name`
6. `source give_some_name/bin/activate`
7. `pip install -r requirements.txt`
8. `python3 books_scraper/scraper.py -h`

## Output format
The output is written as a csv file. For Goodreads data following columns are
written to the csv file:
`["author", "title", "isbn", "language", "avg_rating",
"ratings", "pub_year", "book_format", "pages", "genre"]`

For Google Scholar data, the columns are:
`["author", "title", "citedby", "url", "abstract"]`

** This code is written by taking lot of help from StackOverflow community and
Python API documentation. Greatly appreciated! **