# continuous-software-traceability-thesis

This branch is the simulation branch of the replication package of Rick van Grootveld his thesis. It contains the source code that has been used to produce the results in his thesis. You can run the program by having Python and Docker installed. 

## Project overview
Other branches in this replication package contain
- main
    - This branch contains the data analysis files, the ethics scan, metrics generation files, and what the project is about.
- scalability
    - This branch contains the scalability test of this study. Compared to the simulation branch, this branch contains an extra message protocol between the enrichment service and the knowledge graph service to control the input of the knowledge graph and thus the enrichment.
- prompt engineering
    - This branch contains the prompt engineering that has been done to end up with the prompt that has been used in the document.

## Run the program
To run the program and to replicating the research:

The branch has been set to the settings of using the Qwen model.To use the GPT API, you should have a OpenAI API key to run the GPT model and you should change the global variables in the llm.py file in the enrichment folder to set it to GPT. If you don't have the API key, you can still build the Qwen model using the following steps.

1. After downloading Docker and Python, I used the following constraints for Docker to stabalize the environment. When the program starts without any constraints, Docker and Windows start fighting for resources, causing the program to crash. Therefore, you should add the file .wslconfig to your path: "C:\Users\/user_name\.wslconfig". Save this file with the following content.
the file .wslconfig to your path: "C:\Users\/<user>\.wslconfig"
```
content: [wsl2] 
memory=12GB 
cores=6 
localhostForwarding=true
```

I chose the processers to be 8 because I have 16 processors in total. Make sure that the constraints you save align with the requirements of your hardware. 

2. Then, open the terminal and navigate to the root folder of this project, use the following commands in your terminal to run the program in Docker:
```
//docker-compose build --no-cache

//docker exec -it ollama ollama pull qwen3.5:4b

docker-compose up --build -d
```
This builds the program first, downloads Qwen3.5 4B, and starts the program detached from the terminal. Downloading the model first prevents it from downloading the model at the start, which would run the program without enrichments for 10 minutes.

3. When the program starts, simultanuously run the docker_performance.py file. This file gathers information about the CPU and memory.

## Contact information
If there are any questions, please reach out to me.

GitHub username: RickvGrootveld