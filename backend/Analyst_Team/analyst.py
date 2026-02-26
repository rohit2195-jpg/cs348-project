from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
import os
from dotenv import load_dotenv
from Analyst_Team.tools import save_analysis_to_txt, get_stock_analysis, get_todays_headlines
from webscraping.scrape import todayHeadlines, analysisHeldStock

load_dotenv()

# webscrape the data to make it available

# fill todays headlines in webscraping/todays_headlines.txt
# todayHeadlines() 

# webscrape each f500 stock put it in webscraping/tickerAnalysis
# analysisHeldStock()

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,  
    max_tokens=None,
    timeout=None,
    max_retries=2,
)

agent = create_agent(model, tools=[save_analysis_to_txt, get_todays_headlines, get_stock_analysis])

def generate_report():
    
    analysis_output = agent.invoke(
            {"messages": [{"role": "user", 
                        "content": f""" 
    You are responsible for gathering and analyzing various types of market data to inform trading decisions. 

    Your combined insights form the foundational input for the Researcher Team, ensuring that
    all facets of the market are considered in subsequent decision-making processes.

    Include as many statistics/data as possible from the given information.
    Additionally, always include the ticker/symbol next to the company name when referecned.
    I want you to perform comprehensive analysis on stocks, market, market trends. 

    Produce a very lengthy report on as many stock info, market trends as you can with as much info as possible.
    Your information is vital for future agents to make decisions based on the data.

    Output your analysis to a txt file using your tools. Please use new lines to format your answer, no additionall formatting.   
                        """
            }]}
    )
    



    return analysis_output

