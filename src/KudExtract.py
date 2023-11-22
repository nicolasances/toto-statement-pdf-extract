import pdfquery as pq
import pandas as pd
import xml.etree.ElementTree as ET
from pprint import pprint
import re
import nltk
from nltk.tokenize import RegexpTokenizer
nltk.download('punkt')

class KudExtract:

    number_pattern = re.compile(r'^(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s?([+-]?)$')
    useless_tokens_pattern = re.compile(r'^\s*\+\s*$')
    tokenizer = RegexpTokenizer(r'\w+')
    date_pattern = re.compile(r'\d{2}\.\d{2}\s*$')

    def __init__(self):
        pass

    def process_pdf(self, filepath): 

        # Load PDF and generate XML
        self.__load_pdf_contents(filepath)

        # Extract lines
        lines = self.__extract_lines("kud.xml")

        # Clean up lines
        lines = self.__clean_lines(lines)

        # Filter lines
        lines = self.__filter_lines(lines)

        # Remove tokens that are not needed
        lines = self.__filter_tokens(lines)

        # Create the final list
        data = self.__transform_to_json(lines)

        return data
    
    def __load_pdf_contents(self, filepath): 
        pdf = pq.PDFQuery(filepath)
        pdf.load()
        pdf.tree.write('kud.xml', pretty_print=True)

    def __extract_lines(self, xmlFilename): 
        '''Extract all lines of text present in the XML (representing a PDF)
        
        Parameters: 
        xmlFilename (string): the file name of the xml to load. The XML is the PDF converted into XML.

        Returns: 
        dict: a dictionnary where the key is the identifier (page, line) (e.g. P1L670.11). Each element is a list of tokens belonging on the same line and page
            Example of keys:
            P1L503.007: ['Indestående ', 'Indsat ', 'Bogført ', 'Rente- ']
            P1L492.207: ['Gæld ', 'Hævet ', 'dato ', 'dato ']
            P1L468.447: ['494,42 - ', '3.291,68 ', '+ ', 'Gjensidige Forsikring, D ', '03.10 ', '03.10 ']

        '''
        tree = ET.parse(xmlFilename)
        root = tree.getroot()

        lines = {}

        pages = root.findall(".//LTPage")

        for page in pages: 
            page_num = int(page.get("pageid"))
            
            for line in page.findall(".//LTTextLineHorizontal"):
                y0 = float(line.get("y0"))
                index = "P" + str(page_num) + "L" + str(y0)

                text_element = line.text or line.find(".//LTTextBoxHorizontal").text

                if index in lines: 
                    lines[index].append(text_element)
                else: 
                    lines[index] = [text_element]

        return lines;
    
    def __parse_numbers(self, line): 
        '''Cleans the numbers contained in a given line.
        Cleaning up numbers means moving from '494,42 - ' to a float -494.42

        Parameters: 
        line (list): the list of tokens of the line

        Returns: 
        list: the cleaned line
        '''
        clean_line = []

        for token in line: 

            match = self.number_pattern.match(token.strip())

            if match:
                numeric_part, sign = match.groups()
                numeric_part = numeric_part.replace('.', '').replace(',', '.')  # Replace comma with period for decimal part
                number = float(numeric_part)
                if sign == '-':
                    number = -number
                
                clean_line.append(number)
            else: 
                clean_line.append(token)

        return clean_line
    
    def __remove_useless_tokens(self, line):
        '''Removes tokens that are not needed.
        That is, for example, tokens ' +'

        Parameters: 
        line (list): the line as a list of tokens

        Returns:
        list: the clean line
        '''
        clean_line = []

        for token in line: 

            if isinstance(token, (int, float)): 
                clean_line.append(token)
                continue
            
            match = self.useless_tokens_pattern.match(token)

            if not match: 
                clean_line.append(token)


        return clean_line
    
    def __clean_date(self, line): 
        '''Cleans the date

        Parameters: 
        line (list): the line as a list of tokens

        Returns:
        list: the clean line
        '''
        clean_line = []

        for token in line: 

            if isinstance(token, (int, float)): 
                clean_line.append(token)
                continue

            clean_line.append(token.strip())
        
        return clean_line
    
    def __clean_text(self, line): 
        '''Cleans the text, only keeping words

        Parameters: 
        line (list): the line as a list of tokens

        Returns:
        list: the clean line
        '''
        clean_line = []

        for token in line: 

            if isinstance(token, (int, float)): 
                clean_line.append(token)
                continue

            if self.date_pattern.match(token):
                clean_line.append(token)
                continue

            text_tokens = self.tokenizer.tokenize(token)
            clean_text = ' '.join(text_tokens)

            clean_line.append(clean_text)
        
        return clean_line
    

    def __clean_lines(self, lines): 
        '''Takes the lines and cleans up the numbers and the text
        Cleaning up numbers means moving from '494,42 - ' to a float -494.42
        Cleans up dates (e.g. trims)
        '''

        pattern = re.compile(r'^(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s?([+-]?)$')

        for key in lines.keys():

            # Clean the numbers
            lines[key] = self.__parse_numbers(lines[key])
            
            # Cleans dates
            lines[key] = self.__clean_date(lines[key])

            # Remove useless tokens
            lines[key] = self.__remove_useless_tokens(lines[key])

            # Cleans the text description
            lines[key] = self.__clean_text(lines[key])

        return lines
    
    def __filter_lines(self, lines):
        '''Filter the lines, keeping only the ones corresponding to payments
        
        Parameters: 
        lines (dict): the dictionnary of lines

        Returns: 
        dict: the updated dictionnary
        '''
        clean_lines = {}    

        for key, line in lines.items(): 

            # Count how many numbers this line contains. 
            # If the line contains >= 2 numbers, then it's a valid line, to keep
            num_numbers = sum(isinstance(item, (int, float)) for item in line)

            if num_numbers >= 2: 
                clean_lines[key] = line
        
        return clean_lines
    
    def __filter_tokens(self, lines): 
        '''Filter the tokens, keeping only the ones that are needed
        Removes the saldo
        Removes duplicate dates
        
        Parameters: 
        lines (dict): the dictionnary of lines

        Returns: 
        dict: the updated dictionnary
        '''
        clean_lines = {}    

        for key, line in lines.items(): 

            smallest_number = 10**20
            clean_line = []

            for token in line: 
                
                if isinstance(token, (int, float)): 
                    if token < smallest_number: 
                        smallest_number = token
                    continue
                
                # Check that the token is not already in the list (eliminate duplicates)
                if not token in clean_line: 
                    clean_line.append(token)
            
            clean_line.append(smallest_number)

            clean_lines[key] = clean_line
        
        return clean_lines

    def __transform_to_json(self, lines):
        '''Transforms the provided lines into JSON (dict)

        Parameters: 
        lines (dict): the dictionnary of lines

        Returns: 
        list: a list of items, each item being a JSON with the key expense information
        '''
        data = []

        for line in lines.values(): 

            json = {}
            
            for token in line: 

                if isinstance(token, (int, float)): 
                    json["amount"] = token
                    continue

                if self.date_pattern.match(token):
                    json["date"] = token
                    continue

                json["text"] = token
            
            data.append(json)
        
        return data
    
