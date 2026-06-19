# continuous-software-traceability-thesis

## Run the program
Use the following command to run the program in Docker:
```

//docker-compose build --no-cache

//docker exec -it ollama ollama pull qwen3.5:4b

docker-compose up --build -d
```

Add the file .wslconfig to your path: "C:\Users\/<user>\.wslconfig"
With the content: 
[wsl2]
memory=12GB
cores=6
localhostForwarding=true
