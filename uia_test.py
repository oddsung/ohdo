import time
from pywinauto import Application

def test_notepad_uia():
    try:
        print("Starting Notepad...")
        app = Application(backend="uia").start("notepad.exe")
        time.sleep(2) # Give it time to render
        
        print("Connecting to main window...")
        main_win = app.window(title_re=".*메모장.*", class_name="Notepad")
        main_win.wait('ready', timeout=5)
        
        print("Main window found. Title:", main_win.window_text())
        
        print("Looking for MenuBar...")
        # Print control identifiers to see what it actually looks like
        # We will save to a file to avoid massive console output
        with open("uia_dump.txt", "w", encoding="utf-8") as f:
            # print_control_identifiers can print to a file in some versions, but we can capture stdout or just do it recursively
            pass
            
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
            except Exception as e2:
                print("Failed by auto_id:", type(e2).__name__)
                
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_notepad_uia()
