import time
from pywinauto import Desktop
import subprocess

def test_notepad_desktop():
    try:
        print("Starting Notepad...")
        subprocess.Popen("notepad.exe")
        time.sleep(3) # Give it time to render
        
        print("Connecting to main window via Desktop...")
        # Search the whole desktop for the Notepad window
        desktop = Desktop(backend="uia")
        main_win = desktop.window(title_re=".*메모장.*", class_name="Notepad", found_index=0)
        main_win.wait('ready', timeout=5)
        
        print("Main window found. Title:", main_win.window_text())
        
        print("Dumping controls to text file...")
        main_win.print_control_identifiers(filename="uia_dump.txt")
            
        print("Looking for File menu...")
        try:
            file_menu = main_win.child_window(title="파일", control_type="MenuItem")
            file_menu.wait('exists', timeout=5)
            print("FOUND '파일' using title='파일'")
            file_menu.invoke()
        except Exception as e:
            print("Failed to find using title='파일':", type(e).__name__)
            
            try:
                print("Trying by auto_id='File'...")
                file_menu = main_win.child_window(auto_id="File", control_type="MenuItem")
                file_menu.wait('exists', timeout=5)
                print("FOUND '파일' using auto_id='File'")
                file_menu.invoke()
                print("Invoked successfully.")
            except Exception as e2:
                print("Failed by auto_id:", type(e2).__name__)
                
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_notepad_desktop()
