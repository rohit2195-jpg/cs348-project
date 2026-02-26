from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def todayHeadlines():
    lines = []
    # reading from the inputs on where to webscrape
    with open('backend/webscraping/sites.txt', "r") as file:
        lines = file.readlines()
    # opening the file to deposit scraped info
    with open('backend/webscraping/todays_headlines.txt', "w") as file:
        for line in lines:
            line = line.strip()
            response = requests.get(line)
            htmlContent = response.text

            # parsing html
            soup = BeautifulSoup(htmlContent, 'html.parser')

            print(soup.title)

            articles = soup.find_all("a", class_="comp mntl-card-list-items mntl-universal-card mntl-document-card mntl-card card card--no-image")
            print(len(articles))

            # only getting the first 6 articles

            for i in range(min(len(articles), 6)):
                # visiting each of the article links to webscrape
                link = articles[i]['href']
                res = requests.get(link)
                htmlContent = res.text
                soup = BeautifulSoup(htmlContent, 'html.parser')

                title_tag = soup.select_one("h1")
                title = title_tag.get_text(strip=True) if title_tag else None

                # adding desired text to content string
                paragraphs = soup.find_all("p")
                content = ""
                for p in paragraphs:
                    p = p.get_text(strip=True)
                    if (len(p) >= 95):
                        content += " " + p

                
                file.write(title + ": " + content + "\n")


            print('----------------------')

        print(lines)

# getting infromation on all f500 stocks
def analysisHeldStock():

    # creating a pypeteering script to read js

    # get all f500 companies
    driver = webdriver.Chrome()
    driver.get("https://stockanalysis.com/list/sp-500-stocks/")

    wait = WebDriverWait(driver, 10)

    table = wait.until(
        EC.presence_of_element_located((By.ID, "main-table"))
    )

    headers = []
    header_elements = table.find_elements(By.TAG_NAME, "th")
    for header in header_elements:
        headers.append(header.text.strip())

    rows = table.find_elements(By.TAG_NAME, "tr")

    data = []
    for row in rows[1:]:
        cols = row.find_elements(By.TAG_NAME, "td")
        if cols:
            data.append([col.text.strip() for col in cols])

    df = pd.DataFrame(data, columns=headers)

    print(df.head())

    driver.quit()

    # Example: get tickers column
    ticker_list = df["Symbol"].to_list()

    
    driver = webdriver.Chrome()

    for ticker in ticker_list:
        with open(f'backend/webscraping/tickerAnalysis/{ticker.lower()}.txt', "w") as file:

            url = f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/"
            driver.get(url)

            time.sleep(3) 

            soup = BeautifulSoup(driver.page_source, "html.parser")
            paragraphs = soup.find_all("p")

            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) >= 50:
                    print(text)
                    file.write(text + "\n\n")

    driver.quit()











