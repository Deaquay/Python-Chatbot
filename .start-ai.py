import os
import sys
from pathlib import Path

def list_ai_options(base_path):
    """
    Lists AI options based on the *_system.txt files in the specified directory.
    """
    ai_files = list(base_path.glob("*_system.txt"))
    options = {str(index): file.stem.replace("_system", "") for index, file in enumerate(ai_files, start=1)}
    return options

def main():
    base_path = Path(__file__).parent
    while True:
        # Display menu
        print("Choose which AI to start by typing its number, or 0 to exit:")
        options = list_ai_options(base_path)
        for index, name in options.items():
            print(f"{index}. {name}")
        print("0. Exit")

        # User input
        choice = input("Enter the number of your choice (0 to exit): ").strip()
        if choice == "0":
            print("Exiting...")
            sys.exit(0)
        
        # Validate choice
        selected_ai = options.get(choice)
        if not selected_ai:
            print("Invalid choice. Please try again.\n")
            continue
        
        # Set API Key (replace with your key)
        os.environ["COHERE_API_KEY"] = "123124-asd-YOUR-API-KEY-asd-53243"

        # Run the selected AI
        script_path = base_path / ".AI-Base.py"
        if not script_path.exists():
            print(f"Error: Script {script_path} not found.")
            sys.exit(1)
        
        print(f"Starting AI: {selected_ai}...")
        os.system(f"python {script_path} {selected_ai}")

        # Pause for the user to return to the menu
        input("Press any key to return to the main menu...\n")

if __name__ == "__main__":
    main()
