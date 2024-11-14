import os
import contextlib
import sys
import cohere
import json
import requests
import wave
import time  # To simulate streaming behavior
import subprocess
import threading
from colorama import Fore, Style, init
from difflib import SequenceMatcher  # For response similarity check
# from TTS.api import TTS  # For Coqui TTS integration

# Ensure a bot name argument is provided
if len(sys.argv) < 2:
    print(Fore.RED + "Error: Please provide the bot name as a command-line argument.")
    sys.exit(1)

# Initialize colorama for Windows compatibility
init(autoreset=True)

# Get the API key from environment variables
api_key = os.getenv("COHERE_API_KEY")

# Initialize the Cohere client with the API key
proxies = {
    'http': os.getenv('HTTP_PROXY'),
    'https': os.getenv('HTTPS_PROXY')
}

# Check the IP address using the proxy at the beginning of the script.
def check_ip():
    try:
        response = requests.get("http://ipinfo.io/ip", proxies=proxies)
        response.raise_for_status()
        print(f"ProxyCheck, Your IP address is: {response.text.strip()}")
    except requests.RequestException as e:
        print(f"Error checking IP address: {e}")
        sys.exit(1)
        
check_ip()

# Initialize the Cohere client without proxies
co = cohere.ClientV2(api_key=api_key)

# Get the bot name from the command-line argument
assistant_name = sys.argv[1]

# Define the path to the system message file based on the bot name
system_message_file = f"{assistant_name}_system.txt"

# Define shared parameters for Cohere chat API
params = {
    "model": "command-r-plus-08-2024",
    # "model": "c4ai-aya-expanse-32b", # 8k limit
    "frequency_penalty": 0.9,  # Penalizes repeated words
    "temperature": 0.7,        # Balances creativity and predictability
    "p": 0.9,
    "safety_mode": "NONE"      # Set safety mode to NONE
}

# Declare the global 'keywords' variable at the top of the script
keywords = {}

# Global list to hold pending keywords
pending_keywords = []

# Load the system configuration from a plaintext file
try:
    system_message = ""
    ai_greeting = ""
    keys_files = []

    with open(system_message_file, 'r') as file:
        lines = file.readlines()
        current_section = "system_message"  # Default to system message section
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):  # Ignore empty lines or comments
            continue
        if stripped_line == "ai_greeting:":
            current_section = "ai_greeting"
        elif stripped_line == "keys_files:":
            current_section = "keys_files"
        elif current_section == "ai_greeting":
            if ai_greeting:
                ai_greeting += " " + stripped_line
            else:
                ai_greeting = stripped_line
        elif current_section == "keys_files":
            keys_files.append(stripped_line)
        else:
            if current_section == "system_message":
                if system_message:
                    system_message += " " + stripped_line  # Continue reading system message
                else:
                    system_message = stripped_line

except FileNotFoundError:
    print(Fore.RED + f"Error: System message file '{system_message_file}' not found.")
    sys.exit(1)

print(f"Loaded system message for bot '{assistant_name}'.\n\nLoaded Keyword files:\n" + "\n".join(keys_files))

# Start with an empty conversation history
history_file = f"{assistant_name}_history.json"

# Ensure the history directory exists
history_dir = os.path.join(os.getcwd(), "history")
os.makedirs(history_dir, exist_ok=True)

def load_history():
    """Load conversation history if the file exists and is not corrupted."""
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                data = f.read().strip()
                if not data:  # If the file is empty
                    print(Fore.YELLOW + "History file is empty. Starting a new conversation.")
                    return [{"role": "system", "content": system_message}]
                history = json.loads(data)
                return history  # Return parsed JSON data
        except (json.JSONDecodeError, IOError):
            print(Fore.RED + "Error: Corrupted or invalid JSON. Starting a new conversation.")
            return [{"role": "system", "content": system_message}]
    return [{"role": "system", "content": system_message}]  # Default to new conversation

def save_history(messages):
    """Save conversation history to a file."""
    with open(history_file, 'w') as f:
        json.dump(messages, f)

def backup_history():
    """Backup the current chat history when the conversation is reset."""
    if os.path.exists(history_file):
        # Find the next available backup number
        backup_number = 1
        while True:
            backup_file = os.path.join(history_dir, f"{assistant_name}_history_{backup_number}.json")
            if not os.path.exists(backup_file):
                break
            backup_number += 1
        
        # Copy the current history file to the backup file
        with open(history_file, 'r') as src, open(backup_file, 'w') as dst:
            dst.write(src.read())
        print(Fore.GREEN + f"Backup created: {backup_file}")

def repeat_last_message(messages):
    """Repeat the last assistant message if it exists."""
    if len(messages) > 1:  # Check if there's more than just the system message
        for msg in reversed(messages):
            if msg['role'] == 'assistant':
                print(Fore.GREEN + f"\n- {assistant_name} (Last Message):\n" + Style.RESET_ALL + f"{msg['content']}")
                break
    else:
        print(Fore.YELLOW + "No previous conversation found.")

# Retry the last response if the user types 'retry'
def retry_last_response(messages, additional_instruction=None):
    """Retry the last user message with an optional additional instruction."""
    if len(messages) > 1:  # Check if there's more than just the system message
        # Find the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]['role'] == 'user' and messages[i]['content'].strip():
                user_message = messages[i]['content'].strip()
                # Remove all messages after this user message (ignoring the last assistant response)
                messages = messages[:i + 1]
                break

        # If additional instruction is provided, add it as a system message before retrying
        if additional_instruction:
            # Strip and validate the additional instruction
            additional_instruction = additional_instruction.strip()
            if not additional_instruction:
                print(Fore.YELLOW + "Additional instruction is empty. Retry aborted.")
                return

            # Add the additional instruction as a system message
            messages.append({"role": "system", "content": additional_instruction})

        # Debug: Print the message history to verify it before the API call
        print(Fore.CYAN + "\nDebug: Message history before retry:\n" + Style.RESET_ALL, json.dumps(messages, indent=2))

        # Call the Cohere chat API with the adjusted message history
        try:
            response = co.chat(
                **params,  # Keep the model and parameters consistent
                messages=messages  # Override the messages parameter with the updated message list
            )

            # Extract the new assistant's response
            assistant_response = response.message.content[0].text  # Adjust the attribute path if necessary

            # Simulate streaming of the assistant's response in chunks
            print(Fore.GREEN + f"\n- {assistant_name} (Retry):\n" + Style.RESET_ALL, end='')
            display_response(assistant_response)  # Stream the response

            # Append the new assistant's response to the message history
            messages.append({"role": "assistant", "content": assistant_response})

            # Save the updated history after the retry
            save_history(messages)

            # Generate speech from the assistant's response
            generate_speech(assistant_response)
        except Exception as e:
            print(Fore.RED + f"Error during retry: {str(e)}")
    else:
        print(Fore.YELLOW + "No valid user message found to retry.")

# Directly print the response instead of streaming in chunks
def display_response(response_text):
    """Directly display the assistant's response without streaming."""
    print(response_text)

def play_audio(output_path):
    """Play audio asynchronously with MPC-HC64."""
    player_path = r"C:\Path\To\Player.exe"
    subprocess.run([player_path, output_path], check=True)

# Add a global toggle for TTS
tts_enabled = False

def generate_speech(text):
    """Generate and stream speech using the xtts-api-server, then play it asynchronously."""
    if not tts_enabled:
        return  # Exit if TTS is disabled
        
    try:
        # Define parameters for the request to the TTS server
        tts_params = {
            "text": text,
            "speaker_wav": "calm_female",  # Use 'calm_female', 'female', or 'male'
            "language": "en"
        }

        # Make a request to the TTS server running on port 8020
        response = requests.get(
            "http://127.0.0.1:8020/tts_stream",
            params=tts_params,
            stream=True,
            proxies={"http": None, "https": None}  # No proxy for local requests
        )

        # Check if the request was successful
        if response.status_code == 200:
            # Define the output path for the audio file
            output_path = "F:\\AI\\LLM\\SillyTavern-Launcher\\output\\out.wav"

            # Save the audio response to a file
            with open(output_path, "wb") as audio_file:
                for chunk in response.iter_content(chunk_size=512):
                    if chunk:
                        audio_file.write(chunk)
            
            # Play the audio file in a separate thread
            threading.Thread(target=play_audio, args=(output_path,), daemon=True).start()

        else:
            print(f"Error: Received status code {response.status_code} from TTS server.")
    except Exception as e:
        print(f"Error generating speech: {e}. Speech synthesis will be skipped.")

def auto_send_recap(messages):
    """Automatically send a recap message if the user types 'recap'."""
    recap_message = "(OOC: Pause Roleplay and lets recap the events. Before we resume i just want to check up on you so you are on the right track in the roleplay. Can you answer these questions for me: 1. What is the plot? 2. What is the setting? 3. What are our goals? 4. What is your role and my role? 5. What is the current situation? Feel free to use OOC at any point if you have any questions.)"
    messages.append({"role": "user", "content": recap_message})
    save_history(messages)
    
# Load the Keyword files specified in the configuration
def load_keywords(keys_files):
    global keywords
    for keys_file in keys_files:
        try:
            print(f"Loading keywords file: {keys_file}")
            with open(keys_file, "r") as file:
                for line in file:
                    line = line.strip()
                    if not line or line.startswith("#"):  # Ignore empty lines or comments
                        continue
                    parts = line.split(";")
                    if len(parts) != 3:
                        print(f"Warning: Invalid format in line '{line}'. Skipping.")
                        continue
                    title, key_string, content = parts
                    # Strip special characters and newlines from keys
                    key_string = key_string.replace('', '').replace('', '')
                    keys = [k.strip() for k in key_string.split(",")]
                    keywords[title] = {
                        "key": keys,
                        "content": content.strip()
                    }
        except FileNotFoundError:
            print(f"Warning: Keys file '{keys_file}' not found. Skipping.")

# Load the filtered keywords from the specified keys files if any are specified
if keys_files:  # Only attempt to load keywords if keys_files is not empty
    load_keywords(keys_files)

# Print the final loaded keywords for debugging purposes
print(Fore.CYAN + f"Loaded keywords: {keywords}" + Style.RESET_ALL)

# Update find_matching_keywords function to reflect the new structure
# This function will collect matching keywords from the input text
def find_matching_keywords(input_text):
    global keywords  # Use the global 'keywords' variable
    matching_keywords = []
    input_text_lower = input_text.lower()  # Lowercase the input for case-insensitive comparison

    for keyword_key, keyword_data in keywords.items():
        # Check if any of the keywords are present in the input (case-insensitive)
        keyword_keys = keyword_data.get('key', [])
        if any(kw.lower() in input_text_lower for kw in keyword_keys):
            matching_keywords.append(keyword_data)

    return matching_keywords


def append_new_keywords(messages, matching_keywords):
    global pending_keywords

    if not matching_keywords and not pending_keywords:
        # print(Fore.YELLOW + "No new or pending keywords to process." + Style.RESET_ALL)
        return

    # Add new keywords to pending list if available
    if matching_keywords:
        # Extract and clean keywords properly
        new_keywords = set()
        for keyword in matching_keywords:
            keyword_label = keyword['key'][0].strip().lower() if 'key' in keyword and len(keyword['key']) > 0 else ''
            if keyword_label not in pending_keywords:
                new_keywords.add(keyword_label)

        # Add the new keywords to the pending list
        pending_keywords.extend(new_keywords)
        # print(Fore.GREEN + f"New keywords added to pending list: {new_keywords}" + Style.RESET_ALL)

    # If there are still no pending keywords, exit
    if not pending_keywords:
        # print(Fore.YELLOW + "No pending keywords after update." + Style.RESET_ALL)
        return

    # Only send the first keyword from the pending list
    keyword_to_send = pending_keywords.pop(0)
    print(Fore.GREEN + f"Processing keyword: {keyword_to_send}" + Style.RESET_ALL)

    # Search for the keyword in the JSON structure
    keyword_content = None
    for keyword_key, entry in keywords.items():
        if keyword_to_send.lower() == keyword_key.lower() or keyword_to_send.lower() in [kw.lower() for kw in entry.get('key', [])]:
            keyword_content = entry.get('content', None)
            break

    # Proceed only if content is found
    if keyword_content:
        # Concatenate the keyword and its content into a concise message
        concatenated_new_keywords = f"!!AI_IGNORE_FORMAT!!\nReference Material:\n - {keyword_to_send}\n{keyword_content}"

        # Wrap the message in square brackets
        concatenated_new_keywords = f"[{concatenated_new_keywords}]"

        # Add it as a 'system' message to provide context without influencing behavior
        messages.append({"role": "system", "content": concatenated_new_keywords})
        # print(Fore.CYAN + f"Added new reference material to context:\n{concatenated_new_keywords}" + Style.RESET_ALL)
    else:
        print(Fore.RED + f"No content found for keyword: '{keyword_to_send}'. Skipping." + Style.RESET_ALL)


# Load the conversation history first
messages = load_history()

# Repeat the last message (if any) after history is loaded
repeat_last_message(messages)

print(f"\n──────────────────────────────────────────\nWelcome to the {assistant_name} Chat! Type 'exit' to quit, 'recap' for an OOC Summary, 'reset' to start a new conversation, 'tts' to toggle tts (server needs to be running and info set in def generate_speech) or 'retry: <instruction>' to retry the last response with (optional) additional instructions.\n\nExample start mess to get the bot on track:\n\n{ai_greeting}\n\n")

# Main loop for chat
while True:
    # Get input from the user
    user_input = input(Fore.CYAN + "\n- You:\n" + Style.RESET_ALL)

    # Sanitize input to handle unexpected or special characters
    user_input = user_input.strip()

    # Ignore empty input
    if not user_input:
        print(Fore.YELLOW + "Input is empty. Please type a message.")
        continue

    # Exit if the user types 'exit'
    if user_input.lower() == 'exit':
        print("Goodbye!")
        break
        
    # Command to toggle TTS
    if user_input.lower() == 'tts':
        tts_enabled = not tts_enabled
        print(f"TTS generation {'enabled' if tts_enabled else 'disabled'}.")
        continue

    # Reset the conversation
    if user_input.lower() == 'reset':
        confirm_reset = input(Fore.YELLOW + "Are you sure you want to reset the conversation? (yes/no): " + Style.RESET_ALL).strip().lower()
        if confirm_reset == 'yes':
            backup_history()  # Backup the current history
            messages = [{"role": "system", "content": system_message}]
            save_history(messages)
            print(Fore.YELLOW + "Conversation reset.")
            continue
        else:
            print(Fore.YELLOW + "Reset cancelled.")
            continue
            
    # Trigger recap if the user types 'recap'
    if user_input.lower() == 'recap':
        auto_send_recap(messages)
        continue

    # Retry the last response if the user types 'retry'
    if user_input.lower().startswith('retry'):
        # Extract additional instructions if provided
        if ':' in user_input:
            additional_instruction = user_input.split(':', 1)[1].strip()
            retry_last_response(messages, additional_instruction)
        else:
            retry_last_response(messages)
        continue

    # Find any matching entries for user input
    matching_keywords = find_matching_keywords(user_input)

    # Append new keywords without splitting multi-word phrases
    append_new_keywords(messages, matching_keywords)

    # Append the user's message (with context) to the message history
    messages.append({"role": "user", "content": user_input})

    # Limit the conversation history to the last 100 messages
    MAX_HISTORY_LENGTH = 100  # Keep the last 100 messages
    if len(messages) > MAX_HISTORY_LENGTH:
        messages = messages[-MAX_HISTORY_LENGTH:]

    # Call the Cohere chat API with the message history
    response = co.chat(
        **params,  # Use the appropriate model and parameters 
        messages=messages
    )
    
    # Extract the assistant's response
    assistant_response = response.message.content[0].text

    # Find any matching keywords for the assistant's response (preemptively influence subsequent messages)
    # matching_keywords_assistant = find_matching_keywords(assistant_response)

    # Append new keywords from assistant's response without splitting multi-word phrases
    # append_new_keywords(messages, matching_keywords_assistant)

    # Display assistant's response
    print(Fore.GREEN + f"\n- {assistant_name}:\n" + Style.RESET_ALL, end='')
    display_response(assistant_response)

    # Append the assistant's response to the message history
    messages.append({"role": "assistant", "content": assistant_response})

    # Limit the conversation history to the last 100 messages
    MAX_HISTORY_LENGTH = 100  # Keep the last 100 messages
    if len(messages) > MAX_HISTORY_LENGTH:
        messages = messages[-MAX_HISTORY_LENGTH:]
    
    # Save the updated history after each interaction
    save_history(messages)

    # Generate speech from the assistant's response
    generate_speech(assistant_response)
