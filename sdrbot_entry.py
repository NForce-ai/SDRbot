import warnings

# Suppress Pydantic V1 compatibility warning usually emitted by LangChain/LangGraph
warnings.filterwarnings(
    "ignore", 
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater"
)

from sdrbot_cli.main import cli_main

if __name__ == "__main__":
    cli_main()
