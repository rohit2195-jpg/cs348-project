from ollama import chat
import json


def test():
    response = chat(model='deepseek-r1:8b', messages=[
    {
        'role': 'user',
        'content': 'Why is the sky blue?',
    },
    ])

    print(response.message.content)
#test()


def getStockOutlook(held_stock):

    file = open("backend/webscraping/todays_headlines.txt", "r")
    contents = file.read()
    file.close()

    messages = [
        {
            "role": "system",
            "content": """
    You are a financial research agent.
    You output ONLY valid JSON.
    No commentary, no markdown, no extra text.
    """
        },
        {
            "role": "user",
            "content": f"""
    Analyze the following news and holdings that appear in the news articles.

    Schema:
    - symbol: string
    - sentiment: number between -1 and 1
    - event_type: string
    - event_magnitude: low | medium | high
    - time_horizon: short_term | medium_term | long_term
    - uncertainty: number between 0 and 1
    - reason: max 25 words
    - held_stock: boolean

    Held stocks: {held_stock}

    News:
    {contents}

    Output a JSON array with the above scheme only.
    """
        }
    ]

    response = chat(model="deepseek-r1:8b", messages=messages)

    raw = response.message.content
    print(raw)

    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError:
        print("Invalid JSON:", raw)


ticker_list = ["AAPL", "NVDA", "MSFT", "AMZN"]
print(getStockOutlook(ticker_list))