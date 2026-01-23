from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import time

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
    with open('backend/webscraping/todays_headlines.txt', "a") as file:
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
                        content += "\n\n" + p

                
                file.write(title + "\n\n" + content + "\n\n")
                file.write('----------------------------------------------------\n\n')


            print('----------------------')

        print(lines)

# getting infromation on stocks currently held
def analysisHeldStock(ticker_list):

    # creating a pypeteering script to read js
    
    driver = webdriver.Chrome()
    with open(f'backend/webscraping/tickerAnalysis/{ticker.lower()}.txt', "w") as file:

        for ticker in ticker_list:
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

    todayHeadlines()

    
ticker_list = ["AAPL", "NVDA", "MSFT", "AMZN"]

print(analysisHeldStock(ticker_list))










