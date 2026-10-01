from langchain_groq import ChatGroq
from langchain_core.tools import tool
import requests
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.agents import create_react_agent, AgentExecutor
from langchain import hub
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# Step 1: Tools
# -----------------------------

search_tool = DuckDuckGoSearchRun()


@tool
def get_weather_data(city: str) -> str:
    """
    This function fetches the current weather data for a given city.
    """
    url = (
        f"https://api.weatherstack.com/current"
        f"?access_key=f07d9636974c4120025fadf60678771b"
        f"&query={city}"
    )

    response = requests.get(url)

    return response.json()


# -----------------------------
# Step 2: Groq LLM
# -----------------------------

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0
)


# -----------------------------
# Step 3: ReAct Prompt
# -----------------------------

prompt = hub.pull("hwchase17/react")


# -----------------------------
# Step 4: Create ReAct Agent
# -----------------------------

tools = [search_tool, get_weather_data]

agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)


# -----------------------------
# Step 5: Agent Executor
# -----------------------------

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=5
)


# -----------------------------
# Step 6: Invoke Agent
# -----------------------------

response = agent_executor.invoke({
    "input": "What is the current temperature of Gurgaon?"
})


print(response)

print("\nFinal Answer:")
print(response["output"])