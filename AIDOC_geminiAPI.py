import ast

import google.generativeai as genai

genai.configure(api_key="{API_KEY}")

def generate_response(prompt: str, folder_list: list) -> str:
    ai_model = genai.GenerativeModel("gemini-2.0-flash-exp")
    response = (ai_model.generate_content("I want you to read following document.\n" + prompt +
                                      "\n\n After reading the document, please decide which folder is the most" +
                                      " relevant to the document and return the folder name only along with percentage you believe folder they are in" +
                                      " eg: folder1,[80,15,5] | folder2,[3,80,17] | folder3,[20,10,70]\n" +
                                      " percentage is between 0 to 100 and order of array for percentage is ordered by following folder list."+
                                      " Please note if any folder name are little bit related should increase accuracy percentage to it too."+"\nFolder list: " + str(folder_list) +
                                      " NOTE: if received message that not found respond as 'No pdf was found,"+
                                      " \nNOTE2: please avoid unnecessary predication when context isn't enough"+
                                      " \nIMPORTANT: format has to be. <foldername>,[percentageFolder1,percentageFolder2,percentageFolder3]>"))
    return response.text

if __name__ == "__main__":
    genai.configure(api_key="{API_KEY}")
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
