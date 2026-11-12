# ironclad-utilities
Specialized CSV wrangling and header-injection utilities built for local data automation.
## 🛠️ Setting up the console level Python tools
1. first you need a version of python3 installed if your on windows I'd suggest installing python via the website then using the `where python` command to figure out where specifically the latest version of python is and copying the location of the version you installed into a shortcut file for later use (you'll need to replace any instance of a command that starts with Python3 with this file location in quotes and add a space and a -m tag with a space after it) if on Linux you should have python by default if not look up how to install it on whatever flavor of linux you are using
2. create a folder you can name it however you want but remember we are going to download the 2 python files in there
3. Click on the `CSVTool.py` file to open a preview and ignore the message that it can't be previewed
4. On the file preview screen, locate the group of 3 buttons in the top-right corner (the first button is labeled **Raw**).
5. Click the 3rd button on the right (the download icon, which shows the tooltip **"Download raw file"** when you hover over it) to save the file to your computer.
6. save it to the folder you made in step 2
7. repeat steps 3 through 7 except instead of `CSVTool.py` use `RawDataTool.py`
8. once you have ensured python is installed then run `pip install venv` if you encounter errors on linux look them up and you should find a way to run this command
9. the next command required is `Python3 venv .venv`
> **Note:** if the command worked you should now see a `(venv)` at the beginning of your command prompt
10. the next command is different based on OS on linux it would be `source .venv/bin/activate` on windows it is `source .venv\Scripts\activate.bat` the `.bat` part is optional but I included it just in case
11. the next command is `pip install psutil duckdb pandas rapidfuzz` wait for this to resolve then move on to the next steps
> **Note:** this last command works reguardless of operating system. When you are done running the tool and you have exited the ui remember to run `deactivate` to exit your venv environment
12. now you need to download the `EULA.txt file` from this repo follow steps 3 through 7 except with the file name as `EULA.txt`
13. okay so now the raw data tool needs a specific file called `templateFile.csv` this file is a one line csv file that line should contain all of the headers for your raw headerless files
14. once you create that file with whatever editor you prefer save it in the folder the tool
# RAW data Tool
## 💻 Using The Tool
1. make sure you are in your venv environment we set up in the the setup instructions if you don't have the `(venv)` at the beginning of your command prompt refer to step 4 of the setup steps for what command to run
2. once in your venv run `Python3 RawDataTool.py` a UI window should appear
3. then click the <kbd>Add Files...</kbd> button near the top of the window and next to the white box labeled Input Headless Files then select your files for the current year using windows file explorer
5. then select either Chronological or Reverse Chronological depending on what you need but please use same order for all your files 
> **Note:** the default is Chronological if unsure use that
6. once you are done naming the output file click the <kbd>Merge & Apply Headers</kbd> button
7. press the <kbd>Okay</kbd> button on the success prompt and check the folder where your output is for a headered file with dates ordered by whatever you selected in step 4
> **Note:** now this file is ready for the next tool
8. to create the next file hit the <kbd>Clear All</kbd> button (located below the <kbd>Remove Selected</kbd> button and next to the white box that displays your file inputs)
9. Now repeat steps 3 through 8 until all headered year files have been properly generated
# CSV_TOOL
## 💻 Using The Tool
1. to start the tool make sure you are in your venv environment we set up in the the setup instructions if you don't have the `(venv)` at the beginning of your command prompt refer to step 4 of the setup steps for what command to run
2. once in your venv run `Python3 CSVTool.py` once the ui pulls up move on
4. one more thing you'll need to do select other at the top of the tool because Carbon is for a different use case
### 1. Selecting The Input and Output Files
1. Next you will need to hit the <kbd>Browse...</kbd> button in the program window next to the `input file:` label and after the white input box
2. Navigate to your data file's location using windows file explorer and select the file
3. If you want to use multiple files here hit the <kbd>+ Add Input File</kbd> button at the bottom of the file options box until you have enough input file items (if you hit this button too many times just use the <kbd>Remove</kbd> button (it's the last button) on any file inputs that are not needed) then repeat steps 2 and 3 until all input files have been selected
> **Optional Step 4:** the output file will automatically name itself after your input file's name with `_processed.csv` on original file name (it uses the first file name) if you do not want the output file to be named this way please click the <kbd>Browse...</kbd> button on the end of the input labeled output file and navigate to the place you would like to have your output file then name it whatever you want
### 2. Selecting The Fields
1. There are 2 ways to input fields if you have a preset file skip to step 4 if not go through steps 2 and 3 and skip step 4
2. use the searchable drop down menu to select your fields
3. once you select the fields using the searchable drop down you can rename them in the output column renaming menu
4. if you have a 2 line preset file load it in the input labeled Header Preset File (2-line): by clicking the <kbd>Apply Preset File</kbd> button and then using file explorer to navigate to your preset csv file and select it the tool will auto-load the fields in your preset and rename them according to what you have set in the second line of your preset file
### 3. Selecting the Dates
1. please enter a comma separated list of start dates into the field named Start Dates and then a respective list of end dates into the field labeled End Dates please make sure you follow the requirements below when entering dates
> **Important Requirements:** It is important that you make sure to enter an equal amount of start and end dates. it is important you follow the format that the program asks for as anything not in this format will generate malformed files and possibly require manual clean up (see troubleshooting for what to do if this does happen). Also remember any dates not present in your data files should not be used so make sure you know the date ranges of your files before searching(see troubleshooting if this happens).
2. once you have correctly entered the dates hit the <kbd>Start Processing</kbd> button on the bottom left of the window next to the <kbd>Show Debug Window</kbd> button.
> **Note:** the Show debug window button is only for finding problems with the application and you should not need it
### 4. Checking The Output File
1. after the processing is finished there should be a pop up saying the processing completed successfully click the <kbd>okay</kbd> button
2. now open the output file with whatever program you wish and check that your filtered data is there
> **Note:** if you kept the default it will have made the output in the input file folder with the same name as the first input file (without the .csv) plus `_processed.csv` on the end of it
## 🪛 trouble shooting:
1. if the installer has been run with an outdated token skip to step 4 if you have accidentally entered in correct date formats if you entered incorrect dates and generated malformed output please search where you put your output file for what you named it and delete any files you find
3. go back to the tool/installer and correct your input and try again if there are no issues now then return to whatever you were doing and DO NOT continue to steps 4 and 5 as they either should have already been followed or they do not concern you. 
4. go to your program files in windows and delete the folder called `CSVTOOL` you will need administrator privaleges to do that so when it prompts you select yes
5. go back to step 3
