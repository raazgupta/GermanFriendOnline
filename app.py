from flask import Flask, render_template, request, session
import csv
import openai
import os
import random
from datetime import datetime, timedelta

file_path = "A1Wortlist.csv"

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SESSION_SECRET_KEY')


def recreate_wortlist():
    input_file = "A1Wortlist-backup.csv"
    output_file = "A1Wortlist.csv"

    # Read the file and process each line
    with open(input_file, 'r') as file:
        lines = file.readlines()

    processed_lines = []

    for index, line in enumerate(lines, start=1):
        stripped_line = line.rstrip()  # Remove trailing spaces
        if index == 1:
            modified_line = "Wort, reviewFrequency, reviewDate"
        else:
            modified_line = stripped_line + ',,'  # Add two commas to the end
        processed_lines.append(modified_line + '\n')  # Add newline character

    # Write the processed lines back to the same file
    with open(output_file, 'w') as file:
        file.writelines(processed_lines)

    print("File processing complete.")


def get_completion_from_messages(messages, model="gpt-3.5-turbo", temperature=0.0, max_tokens=500):
    openai.api_key = os.getenv('OPENAI_API_KEY')
    # print("Get completion message: ", messages)
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message["content"]


def chooseSelectedWords():
    # Go through the file
    # Add 10 words with today's date or earlier to selected words as array: [word, line number in wortLines]
    # Also in the case that 10 words are not found, keep an array of [word,line number] that do not have reviewData
    # Then check for the number of not found words,
    # and choose that number from the array in random and add to the selected words array
    wortLines = []
    selected_words_lineNumber = []
    not_reviewed_words = []
    number_burned = 0
    with open(file_path, 'r') as file:
        # num_lines = sum(1 for line in file)
        # print(f"num_lines: {num_lines}")
        for lineNumber, line in enumerate(file, start=0):
            line = line.strip()
            lineElements = line.split(',')
            wortLines.append(line.split(','))
            if lineNumber >= 1:

                word = lineElements[0]
                reviewFrequency = lineElements[1]
                reviewDateString = lineElements[2]

                if reviewDateString == "":
                    not_reviewed_words.append([word, lineNumber])
                elif reviewFrequency != "B":
                    reviewDateObject = datetime.strptime(reviewDateString, "%Y-%m-%d").date()
                    today = datetime.now().date()
                    if reviewDateObject <= today and len(selected_words_lineNumber) < 10:
                        selected_words_lineNumber.append([word, lineNumber])
                elif reviewFrequency == "B":
                    number_burned = number_burned + 1

    print("Number of selected words using reviewDate:", len(selected_words_lineNumber))

    # Check if selected_words has 10 orders or add random words to it
    num_selected_words = len(selected_words_lineNumber)
    if num_selected_words < 10:
        num_missing = 10 - num_selected_words
        if num_missing <= len(not_reviewed_words):
            random_word_indices = random.sample(range(0, len(not_reviewed_words)), num_missing)
        else:
            random_word_indices = random.sample(range(0, len(not_reviewed_words)), len(not_reviewed_words))
        for random_index in random_word_indices:
            selected_words_lineNumber.append(not_reviewed_words[random_index])

    print("Number of selected words after adding random:", len(selected_words_lineNumber))

    # Create a list of selected words
    selected_words = []
    for selected_word_lineNumber in selected_words_lineNumber:
        selected_words.append(selected_word_lineNumber[0])


    percentage_burned = number_burned / (len(wortLines) - 1)

    return wortLines, selected_words_lineNumber, selected_words, percentage_burned


def create_story(selected_words, temperature=0.0):
    # Prompt to create German Story
    # print("German Story temperature: ", temperature)
    messages = [
        {'role': 'system',
         'content': """
         You are a German teacher. 
         """
         },
        {'role': 'user',
         'content': f"""
            Write a story in German with maximum 3 sentences.
            Only use words that are from the Goethe-Zertifikat A1 vocabulary list. 
            Make sure these words are in the story: {",".join(selected_words)}
         """
         },
    ]

    # Print story in German
    response = get_completion_from_messages(messages, temperature=temperature)
    print("German Story:")
    print(response)
    # input()

    messages.append(
        {'role': 'assistant',
         'content': response
         }
    )

    return messages, response



def translate_to_English(messages):
    messages.append(
        {'role': 'user',
         'content': 'Translate this German Story to English.'
         }
    )

    # Print story in English
    response = get_completion_from_messages(messages)
    print("English translation:")
    print(response)
    input()




def save_to_csv(wortLines):
    # Write data to CSV file
    with open(file_path, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        for row in wortLines:
            csv_writer.writerow(row)

@app.route('/')
def index():
    # anki(selected_words_lineNumber, wortLines)
    # translate_to_English(messages)
    # save_to_csv(wortLines)
    return render_template('index.html')

@app.route('/germanStory', methods=['POST'])
def germanStory():
    wortLines, selected_words_lineNumber, selected_words, percentage_burned = chooseSelectedWords()
    messages, response = create_story(selected_words, temperature=percentage_burned)

    result_data = {
        'germanStoryString': response,
        'percentageBurned': percentage_burned * 100
    }

    session['selected_words_position'] = 0
    session['selected_words_lineNumber'] = selected_words_lineNumber

    return render_template('germanStory.html', result = result_data)

@app.route('/anki', methods=['POST'])
def anki():

        selected_words_lineNumber = session['selected_words_lineNumber']
        selected_words_position = session['selected_words_position']

        wort = selected_words_lineNumber[selected_words_position][0]

        result_data = {
            'wort': wort,
            'number': selected_words_position + 1
        }

        return render_template('anki.html', result = result_data)

'''
@app.route('/ankiTranslate', methods=['POST'])
def anki_translate():
    # Get the English translation using OpenAI
    messages = [
        {'role': 'system',
         'content': """
         You are a German teacher. 
         """
         },
        {'role': 'user',
         'content': "One Word English translation for: Klima"
         },
        {'role': 'assistant',
         'content': "Climate"
         },
        {'role': 'user',
         'content': f"One Word English translation for: {wort}"
         },
    ]
    response = get_completion_from_messages(messages, temperature=0)
    user_input = input(response + "\n")
    # Request for next Frequency
    currentFrequency = wortLines[lineNumber][1]
    freq_input = ""
    if currentFrequency == "":
        freq_input = input("Review again Tomorrow (T) or in 1 Week (W): ")
    elif currentFrequency == "T":
        freq_input = input("Review again Tomorrow (T) or in 1 Week (W): ")
    elif currentFrequency == "W":
        freq_input = input("Review again Tomorrow (T) or in 1 Month (M): ")
    elif currentFrequency == "M":
        freq_input = input("Review again Tomorrow (T) or in 3 Months (3M): ")
    elif currentFrequency == "3M":
        freq_input = input("Review again Tomorrow (T) or is it Burned in memory (B): ")
    elif currentFrequency == "B":
        freq_input = "B"
        print("This word is Burned in memory\n")

    # Based on next Frequency update the review date
    today = datetime.now().date()
    nextReviewDate = ""
    if freq_input == "":
        freq_input = "T"
    if freq_input == "T":
        nextReviewDate = today + timedelta(days=1)
    elif freq_input == "W":
        nextReviewDate = today + timedelta(days=7)
    elif freq_input == "M":
        nextReviewDate = today + timedelta(days=30)
    elif freq_input == "3M":
        nextReviewDate = today + timedelta(days=90)
    elif freq_input == "B":
        nextReviewDate = today

    # print(f"{wort} line number: {lineNumber}\n")
    wortLines[lineNumber][1] = freq_input
    wortLines[lineNumber][2] = nextReviewDate.strftime("%Y-%m-%d")

    print('\n')
'''

if __name__ == '__main__':
    app.run(debug=True)