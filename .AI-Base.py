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
import logging
from typing import Dict, List, Any, Optional
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

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s: %(message)s',
    filename='keyword_processing.log'
)

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

# Load the Keyword files specified in the configuration
class KeywordManager:
    def __init__(self):
        """
        Initialize the KeywordManager with tracking mechanisms.
        
        Attributes:
        - keywords: Dictionary of all loaded keywords
        - processed_keywords: Set to track processed keywords
        - pending_keywords: Queue of keywords to be processed
        """
        self.keywords: Dict[str, Dict[str, Any]] = {}
        self.processed_keywords: set = set()
        self.pending_keywords: List[str] = []

    def load_keywords(self, keys_files: List[str]) -> None:
        """
        Load keywords from specified files with enhanced error handling.
        
        Args:
            keys_files (List[str]): List of keyword file paths
        """
        for keys_file in keys_files:
            try:
                with open(keys_file, "r") as file:
                    for line in file:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        
                        try:
                            title, key_string, content = line.split(";", 2)
                            
                            # Clean and process keys
                            keys = [k.strip().lower() for k in key_string.split(",") if k.strip()]
                            
                            # Add to keywords dictionary
                            for key in keys:
                                self.keywords[key] = {
                                    "title": title,
                                    "keys": keys,
                                    "content": content.strip()
                                }
                            
                            logging.info(f"Loaded keyword: {title}")
                        
                        except ValueError as parse_err:
                            logging.error(f"Invalid keyword format in file {keys_file}: {line}. Error: {parse_err}")
            
            except FileNotFoundError:
                logging.warning(f"Keyword file not found: {keys_file}")
            except IOError as io_err:
                logging.error(f"Error reading keyword file {keys_file}: {io_err}")

    def find_matching_keywords(self, input_text: str) -> List[Dict[str, Any]]:
        """
        Find keywords matching the input text.
        
        Args:
            input_text (str): Text to search for keywords
        
        Returns:
            List of matching keyword dictionaries
        """
        input_text_lower = input_text.lower()
        matching_keywords = []
        
        for key, keyword_data in self.keywords.items():
            if key in input_text_lower:
                matching_keywords.append(keyword_data)
        
        return matching_keywords

    def queue_new_keywords(self, matching_keywords: List[Dict[str, Any]]) -> None:
        """
        Queue new keywords for processing, avoiding duplicates.
        
        Args:
            matching_keywords (List[Dict]): List of matching keywords
        """
        for keyword in matching_keywords:
            # Prefer the title as a unique identifier
            key_identifier = keyword['title'].lower()
            
            # Only add if not already processed or pending
            if (key_identifier not in self.processed_keywords and 
                key_identifier not in self.pending_keywords):
                self.pending_keywords.append(key_identifier)
                logging.info(f"Queued new keyword: {key_identifier}")

    def process_next_keyword(self) -> Optional[Dict[str, Any]]:
        """
        Process and return the next pending keyword.
        
        Returns:
            Optional dictionary with keyword content, or None if no keywords
        """
        if not self.pending_keywords:
            return None
        
        # Get and remove the first pending keyword
        keyword_to_process = self.pending_keywords.pop(0)
        
        # Mark as processed
        self.processed_keywords.add(keyword_to_process)
        
        # Retrieve keyword details
        keyword_entry = self.keywords.get(keyword_to_process)
        
        if keyword_entry:
            logging.info(f"Processing keyword: {keyword_to_process}")
            return {
                "formatted_content": self._format_keyword_message(
                    keyword_entry['title'], 
                    keyword_entry['content']
                )
            }
        
        logging.warning(f"No content found for keyword: {keyword_to_process}")
        return None

    def _format_keyword_message(self, title: str, content: str) -> str:
        """
        Format the keyword content for injection into chat history.
        
        Args:
            title (str): Keyword title
            content (str): Keyword content
        
        Returns:
            Formatted message string
        """
        return (
            "!!AI_IGNORE_FORMAT!!\n"
            f"Reference Material:\n"
            f" - {title}\n"
            f"{content}"
        )

# Initialize the KeywordManager
keyword_manager = KeywordManager()
keyword_manager.load_keywords(keys_files)

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
def retry_last_response(
    messages: List[Dict[str, str]], 
    co, 
    params: Dict[str, Any], 
    additional_instruction: Optional[str] = None
) -> Dict[str, str]:
    """
    Retry the last response with optional additional context.
    
    Args:
        messages (List[Dict]): Current conversation messages
        co (Cohere Client): Cohere API client
        params (Dict): API parameters
        additional_instruction (Optional[str]): Extra context for retry
    
    Returns:
        Dict with the new assistant response
    """
    try:
        # Find the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]['role'] == 'user':
                # Trim messages to last user message
                retry_messages = messages[:i+1]
                break
        
        # Add additional instruction if provided
        if additional_instruction:
            retry_messages.append({
                "role": "system", 
                "content": f"[Additional Retry Instruction: {additional_instruction}]"
            })
        
        # Call Cohere API with adjusted messages
        response = co.chat(
            **params,
            messages=retry_messages
        )
        
        # Extract and return response
        return {
            "message": response.message.content[0].text,
            "messages": retry_messages
        }
    
    except Exception as e:
        logging.error(f"Retry failed: {e}")
        return {
            "message": f"Error during retry: {str(e)}",
            "messages": messages
        }

# Directly print the response instead of streaming in chunks
def display_response(response_text):
    """Directly display the assistant's response without streaming."""
    print(response_text)

def play_audio(output_path):
    """Play audio asynchronously with MPC-HC64."""
    player_path = r"F:\Users\xxxx\scoop\apps\k-lite-codec-pack-full-np\current\MPC-HC64\mpc-hc64.exe"
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
            retry_result = retry_last_response(messages, co, params, additional_instruction)
        else:
            retry_result = retry_last_response(messages, co, params)

        # Update the messages list with the retry result
        messages = retry_result['messages']

        # Display and handle the assistant's response immediately after retry
        assistant_response = retry_result['message']
        print(Fore.GREEN + f"\n- {assistant_name} (Retry):\n" + Style.RESET_ALL, end='')
        
        # Display the assistant response
        display_response(assistant_response)

        # Append the assistant's response to the message history
        messages.append({"role": "assistant", "content": assistant_response})

        # Save the updated history after retry
        save_history(messages)

        # Generate speech from the assistant's response
        generate_speech(assistant_response)

        # Continue to the next iteration
        continue

    # Find any matching entries for user input
    matching_keywords = keyword_manager.find_matching_keywords(user_input)

    # Queue new keywords if found
    keyword_manager.queue_new_keywords(matching_keywords)
    
    # Process the next keyword and add it to the message history if available
    keyword_content = keyword_manager.process_next_keyword()
    if keyword_content:
        messages.append({
            "role": "system",
            "content": keyword_content['formatted_content']
    })

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
