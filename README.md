# Python-Chatbot
Simple chat script that connects to cohere's api.

# Installation
### Auto
Check .Install.bat contents so you know what it does. And then run it.  
This will install python module UV and build a venv in cwd, and install other modules into the venv.

### Manual
If you know what you're doing: Create the env/venv you want to use, install setuptools wheel cohere to the env/venv.

### Setup
Input your proxy adress by changing set HTTP_PROXY in .start-ai.bat  
or  
Comment out set HTTP_PROXY in .start-ai.bat.

Set and save API keys there for easy management.

Drop <name>_system.txt files into cwd. See Jailbreak_system.txt, Aina_system.txt and Aria_system.txt for different formats that work, plaintext, json & compressed.  
Also take note of structure, the files have 3 sections, it's system_prompt from start ( starts reading doc as system_prompt, no section needed ) to  ai_greetings: section ( text to appear when bot is started. Not part of prompt, just for sake of copy pasting start  message. ), and then keys_files: section ( .txt files with keywords to inject data to ai at mention of a keyword. one file per line under keys_files: ) see example files.

Keywords files can be anywhere. Just input one filepath per row under keys_files: in Name_system.txt. No quotes.

**Format of keywords file.txt:**

title;word,word2,word3;Information to inject to ai.  
title2;word2,word4,word5;Information to inject to ai.

ex: Capital;city,capital,Metropolis;Some information about capital that bot should know if city, capital or metropolis is mentioned.

### Commands
- TTS: The tts command enables tts, but you need to host your own, and input info in the tts definition in the py file to use it.
- Retry: Removes last message and tells api to retry it to regenerate it.
- Reset: Resets chat to start. Saves history.
- Recap: Sends a message to pause RP and recap events. This is to break AI out of loops and bad behavior. Also so you know the ai isn't confused.
- Exit: Quit, history is saved and resumed when you return. Reset history with reset command.

### Broken/TODO
- "retry: instructions" command is broken.  
- keywords files might be broken