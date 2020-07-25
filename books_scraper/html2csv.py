import os
import glob
import csv
import re
import lxml
import traceback
from pathlib import Path
from bs4 import BeautifulSoup

def get_selectors(sel_file):
    sel_list = []
    with open(sel_file, 'r') as f:
        sel_list = f.readlines()
    return sel_list


def extract_many(soup, sel):
    pass

def extract_one(soup, sel):
    pass



