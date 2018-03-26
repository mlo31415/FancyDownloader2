import re as Regex
import collections
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Program to download the complete history of a Wikidot wiki and maintain a local copy.
# The downloads are incremental and restartable.

# The site history data will be kept in the directory Site History
# The structure is a bit complex:
# Top level contains management files plus directories A-Z plus Misc
# Each of those directories contains directories A-Z plus Misc.
#   This arrangement is to prevent there from being too main directories in any drectory, since some Windows tools don't handle thousands of directories well
#   And Fancy 3 has nearly 26,000 pages already.
#   The complete history of individual pages will be contain in directories named the same as the page and stored in the directory hierarchy according to its first two characters
# The complete history of a page xyz will this be stored in directory X/Y/xyz
# xyz will contain numbered directories, each storing a single version.  I.e., xyz/2 will contain the details of version 2 of page xyz.
# The program will guarantee that all version directories will be complete: If a directory exists, it is complete
#   For this reason, it will be possible to prevent HistoryDownloader from attempting to download a specfic version by creating an empty version directory
# The version directories will be as similar as possible to the directories created by FancyDownloader

# Our overall strategy will be to work in two phases.
#   In the first phase -- initial creation of the local site history -- we will run through the pages from least-recently-updated to most-recently-updated
#       We will keep a local list (stored in the root of the site history structure) of all the pages we have completed.
#       The list will be in order, beginning with the oldest. We will use this list and the corresponding list from Wikidot to determine what to do next.
#       (Going along the list from Wikidot and comparing it with the list stored locally, the first page found on the wikidot list that isn't stored locally is the next to be downloaded.
#   The second phase is maintenance of a complete initial download
#       In this phase we compare recently updated pages with their local copies and down load whatever increments are new

# The process of getting a historical page is complex and requires parsing a lot of HTML in a pseudo-browser.
#   (The history pages are the result of javascript running and not html, so we can't use Beautiful Soup. We will try to use Selenium, which essentially contains its
#     own internal web browser.)

# Start developing the code by figuring out how to read the history of *one* page (randomly selected to be "Balticon 7").

# Open the Fancy 3 page
browser = webdriver.Firefox()
browser.get("http://fancyclopedia.org/balticon-7")

# Find the history button and press it
elem = browser.find_element_by_id('history-button')
elem.send_keys(Keys.RETURN)

# Wait until the history list has loaded
wait = WebDriverWait(browser, 10)
wait.until(EC.presence_of_element_located((By.ID, 'revision-list')))

# Get the history list
div=browser.find_element_by_xpath('//*[@id="revision-list"]/table/tbody')
historyElements=div.find_elements_by_xpath("tr")[1:]    # The first row is column headers, so skip them.

# Note that the history list is from newest to oldest
# The structure of a line is
#       The revision number followed by a "."
#       A series of single letters (these letters label buttons)
#       The name of the person who updated it
#       The date
#       An optional comment
# This calls for a Regex

rec=Regex.compile("^"                       # Start at the beginning
                "(\d+). "                   # Look for a number at least one digit long followed by a period and space
                "([A-Z])"                   # Look for a single capital letter
                "( V S R | V S )"           # Look for either ' V S ' or ' V S R '
                "(.*)"                      # Look for a name
                "(\d+ [A-Za-z]{3,3} 2\d{3,3})"  # Look for a date in the 2000s of the form '20 Feb 2017'
                "(.*)$")                    # Look for an optional comment

historyList=[]
HistoryLine=collections.namedtuple("HistoryLine", "Number, Type, Name, Date, Other")
for el in historyElements:
    t=el.text
    m=rec.match(t)
    # The greedy capture of the user name captures the 1st digit of 2-digit dates.  This shows up as th used name ending in a space followed by a single digit.
    # Fix this
    gps=m.groups()
    t=gps[3]
    if t[-2:-1] == " " and t[-1:].isdigit():
        gps=(gps[0], gps[1], gps[3][:-2], t[-1:]+gps[4], gps[5])
    else:
        gps=(gps[0], gps[1], gps[3], gps[4], gps[5])
    historyList.append(HistoryLine(*gps))
    i=0

i=0