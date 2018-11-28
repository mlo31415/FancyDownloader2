import re as Regex
import xml.etree.ElementTree as ET
import os
import pathlib
import Helpers
import urllib.request
import unidecode
import time
from datetime import datetime
import dateutil
import dateutil.parser
from xmlrpc import client
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common import exceptions as SeEx

# This is based on HistoryDownloader's approach to downloading Fancy2, but downloads *only* the current version of each page -- it does not download history.
# Accordingly, the structure of each page's data is a bit different.

# Program to download the complete history of a Wikidot wiki and maintain a local copy.
# The downloads are incremental and restartable.

# The site history data will be kept in the directory Site History
# The structure is a bit complex:
# Top level contains management files plus directories A-Z plus Misc
# Each of those directories contains directories A-Z plus Misc.
#   This arrangement is to prevent there from being too main directories in any drectory, since some Windows tools don't handle thousands of directories well
#   And Fancy 3 has nearly 29,000 pages already.
#   The complete history of individual pages will be contain in directories named the same as the page and stored in the directory hierarchy according to its first two characters
# The complete history of a page xyz will this be stored in directory X/Y/xyz
# xyz will be similar to what is created by FancyDownloader:
#   source.txt -- contains the source of that version of the page
#   metadata.xml -- and xml file containing the metadata
#           <updated_by> (name of used who did the update)
#           <updated_at> (date and time of update)
#           <tags> (a comma-separated list of tags)
#           <type>  (the kind of update: new, edit, changetags, newfile, removefile, deletepage)
#           <comment> (the update comment, if any)
#           <title>  (the page's title)
#           <files_deleted>  (if a file was deleted, its name)
#   files  -- Files will be saved at the top level.

# Our overall strategy will be to work in two phases.
#   In the first phase -- initial creation of the local site history -- we will run through the pages from least-recently-updated to most-recently-updated
#       We will keep a local list (stored in the root of the site history structure) of all the pages we have completed.
#       The list will be in order, beginning with the oldest. We will use this list and the corresponding list from Wikidot to determine what to do next.
#       (Going along the list from Wikidot and comparing it with the list stored locally, the first page found on the wikidot list that isn't stored locally is the next to be downloaded.
#   The second phase is maintenance of a complete initial download
#       In this phase we compare recently updated pages with their local copies and down load whatever increments are new

# Read and save the history of one page.
# HistoryRoot is root of all history files
def DownloadPage(browser, siteRoot, pageName, justUpdate):

    # Open the requested Fancy 3 page in the browser
    browser.get("http://fancyclopedia.org/"+pageName+"/noredirect/t")

    # Get the first two letters in the page's name
    # These are used to disperse the page directories among many directotoes so as to avoid having so many subdirectores that Windows Explorer breaks when viewing it
    d1=pageName[0]
    d2=d1
    if len(pageName) > 1:
        d2=pageName[1]

    # Page found?
    errortext="The page <em>"+pageName.replace("_", "-")+"</em> you want to access does not exist."
    if errortext in browser.page_source:
        print("*** Page does not exist: "+pageName)
        return

    # Find the Edit button and press it
    browser.find_element_by_id('edit-button').send_keys(Keys.RETURN)
    time.sleep(0.5)     # Just-in-case

    # Wait until the edit box has loaded
    try:
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.ID, 'textarea-id')))
    except:
        print("***Oops. Exception while waiting for the edit text area to load in "+pageName+":  Retrying")
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.ID, 'textarea-id')))

    el=browser.find_element_by_id('edit-page-form')
    source=el.find_element_by_xpath('//*[@id="edit-page-textarea"]/text()').text

    with open(os.path.join(dir, "source.txt"), 'a') as file:
        file.write(unidecode.unidecode_expect_nonascii(source))

    # Update the donelist
    with open(os.path.join(siteRoot, "donelist.txt"), 'a') as file:
        file.write(pageName+"\n")

    return


#--------------------------------------------------------
# Read and save the history of one page.
# Directory is root of all history
def GetPageDate(browser, directory, pageName):

    # Open the Fancy 3 page in the browser
    browser.get("http://fancyclopedia.org/"+pageName+"/noredirect/t")

    # Page found?
    errortext="The page <em>"+pageName.replace("_", "-")+"</em> you want to access does not exist."
    if errortext in browser.page_source:
        print("*** Page does not exist: "+pageName)
        return None

    # Look for the "page-info" inside the "page-options-container"
    try:
        pageInfoDiv=browser.find_element_by_xpath('//*[@id="page-info"]')
    except SeEx.NoSuchElementException:
        pageInfoDiv=None
    except:
        print("***Oops. Exception while looking for page-info div in "+pageName)
        return None

    s=pageInfoDiv.text
    loc=s.find("last edited:")
    if loc == -1:
        print("***Oops. couldn't find 'last edited:' in "+pageName)
        return None
    loc=loc+len("last edited:")
    s=s[loc:].strip()

    loc=s.find(",")
    if loc == -1:
        print("***Oops. couldn't find trailing comma after 'last edited:' in "+pageName)
        return None
    s=s[:loc].strip()

    return dateutil.parser.parse(s, default=datetime(1, 1, 1))


#===================================================================================
#===================================================================================
#  Do it!

# Settings
siteDirectory="I:\Fancyclopedia Site2"
ignorePages=[]      # Names of pages to be ignored
ignorePagePrefixes=["system_", "index_", "forum_", "admin_", "search_"]     # Prefixes of names of pages to be ignored

# Instantiate the web browser Selenium will use
browser=webdriver.Firefox(executable_path=r'C:\Windows\system32\geckodriver.exe')

# Get the magic URL for api access
url=open("url.txt").read()

# Now, get list of recently modified pages.  It will be ordered from least-recently-updated to most.
# (We're using composition, here.)
print("Get list of all pages from Wikidot, sorted from most- to least-recently-updated")
listOfAllWikiPages=client.ServerProxy(url).pages.select({"site" : "fancyclopedia", "order": "updated_at"})
listOfAllWikiPages=[name.replace(":", "_", 1) for name in listOfAllWikiPages]   # ':' is used for non-standard namespaces on wiki. Replace the first ":" with "_" in all page names because ':' is invalid in Windows file names
listOfAllWikiPages=[name if name != "con" else "con-" for name in listOfAllWikiPages]   # Handle the "con" special case

# Remove the skipped pages from the list of pages
for prefix in ignorePagePrefixes:
    listOfAllWikiPages=[p for p in listOfAllWikiPages if not p.startswith(prefix) ]
listOfAllWikiPages=[p for p in listOfAllWikiPages if p not in ignorePages]      # And the ignored pages

# Get the list of individual pages to be skipped, one page name per line
# If donelist.txt is empty or does not exist, no pages will be skipped
skipPages=[]
if os.path.exists(os.path.join(siteDirectory, "donelist.txt")):
    with open(os.path.join(siteDirectory, "donelist.txt")) as f:
        skipPages = f.readlines()
skipPages = [x.strip() for x in skipPages]  # Remove trailing '\n'

# The problem is how to skip looking at the 25,000+ pages which which have not been updated when doing an incremental update.
# We have the time of last update.
# We have a list of pages from Wikidot sorted by time of last update, but no dates associated.
# At a substantial expense, we can check get the date of last update from the wiki for any page.
# So the strategy is to start with the oldest page and do a binary search for the last page updated *before* the date of last update.

# Load the date of last complete update. (If the file is missing, read everything.)
dlcu=None
if os.path.exists(os.path.join(siteDirectory, "dateLastCompleteUpdate.txt")):
    with open(os.path.join(siteDirectory, "dateLastCompleteUpdate.txt")) as f:
        dlcu = f.readline()
if dlcu == None:
    dlcu="1 Jan 1900"
    print("*** No dateLastCompleteUpdate.txt file found in "+siteDirectory)
dateLastCompleteUpdate=dateutil.parser.parse(dlcu, default=datetime(1, 1, 1))

del dlcu

print("   Date of last compete update is "+str(dateLastCompleteUpdate))

# Find the name of the oldest file newer than this date.  This will be the first file that needs updating.
# We do this using a binary search of the list of pages sorted by date gotten from Wikidot
upperindex=len(listOfAllWikiPages)-1
dateupperindex=GetPageDate(browser, siteDirectory, listOfAllWikiPages[upperindex])
print("   "+listOfAllWikiPages[upperindex]+" at upperindex "+str(upperindex)+" was last updated "+str(dateupperindex))

lowerindex=0
datelowerindex=GetPageDate(browser, siteDirectory, listOfAllWikiPages[lowerindex])
print("   "+listOfAllWikiPages[lowerindex]+" at index "+str(lowerindex)+" was last updated "+str(datelowerindex))

# Do a binary search of the list looking for the last page which was fully downloaded.
while True:
    index=int((upperindex+lowerindex)/2)
    pname=listOfAllWikiPages[index]
    date=GetPageDate(browser, siteDirectory, pname)
    print("   "+pname+" at index " + str(index)+" was last updated "+str(date))

    if date < dateLastCompleteUpdate:
        lowerindex=index
        datelowerindex=date
    else:
        upperindex=index
        dateupperindex=date

    if upperindex-lowerindex == 1:
        break

print(str(len(listOfAllWikiPages)-index)+" pages to be downloaded.")
del lowerindex, datelowerindex, upperindex, dateupperindex, date, index

count=0
startPage=pname     # This lets us restart without going back to the beginning. (We can also override this to start at any desired page.)
foundStarter=False
for pageName in listOfAllWikiPages:
    count=count+1
    if pageName == startPage:
        foundStarter=True
    if not foundStarter:
        continue

    if pageName in skipPages:   # This lets us skip specific pages if we wish
        continue

    print("   Getting: "+pageName)
    DownloadPage(browser, siteDirectory, pageName, False)
    if count > 0 and count%100 == 0:
        print("*** "+str(count))


browser.close()