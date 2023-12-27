from flask import Flask, render_template, request, session, redirect, url_for
import openai
from openai import OpenAI
import os
import random
from datetime import datetime, timedelta

file_path = "A1Wortlist.csv"

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SESSION_SECRET_KEY')

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


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
    # openai.api_key = os.getenv('OPENAI_API_KEY')
    # # print("Get completion message: ", messages)
    # response = openai.ChatCompletion.create(
    #     model=model,
    #     messages=messages,
    #     temperature=temperature,
    #     max_tokens=max_tokens,
    # )
    # return response.choices[0].message["content"]

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=messages
    )

    return response.choices[0].message.content

def get_response_from_assistant(assistant_id, thread_id):

    # Run the Assistant
    # The Assistant id and details are on OpenAI API webpage
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # By default run goes into queued state. You can periodically retrieve the Run to check on its status to see if it moved to completed
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
    if run.status == "completed":

        # Print run steps

        run_steps = client.beta.threads.runs.steps.list(
            thread_id= thread_id,
            run_id=run.id
        )
        print(run_steps)


        # Return a list of message objects in descending order as I am interested only in the last response
        thread_messages = client.beta.threads.messages.list(thread_id=thread_id, order="desc")
        #print(thread_messages)
        try:
            # Since the returned list is in descending order take the first message object and extract its text value
            # response = thread_messages.data[0].content[0].text.value
            # Remove annotation text
            message_content = thread_messages.data[0].content[0].text
            annotations = message_content.annotations
            for annotation in annotations:
                message_content.value = message_content.value.replace(annotation.text, "")
            response = message_content.value
        except Exception as e:
            response = f"An unexpected error occurred: {e}"
    else:
        response = "Error: OpenAI Run Failed"

    return response

def chooseSelectedWords():
    # Go through the file
    # Add 10 words with today's date or earlier to selected words as array: [word, line number in wortLines]
    # Also in the case that 10 words are not found, keep an array of [word,line number] that do not have reviewData
    # Then check for the number of not found words,
    # and choose that number from the array in random and add to the selected words array

    # Format [Word, LineNumber, ReviewFrequency, ReviewDateString]
    selected_words_lineNumber = []


    not_reviewed_words = []
    number_burned = 0
    total_lines = 0
    with open(file_path, 'r') as file:
        # num_lines = sum(1 for line in file)
        # print(f"num_lines: {num_lines}")
        for lineNumber, line in enumerate(file, start=0):
            line = line.strip()
            lineElements = line.split(',')
            if lineNumber >= 1:
                word = lineElements[0]
                reviewFrequency = lineElements[1]
                reviewDateString = lineElements[2]

                if reviewDateString == "":
                    not_reviewed_words.append([word, lineNumber, reviewFrequency, reviewDateString])
                elif reviewFrequency != "B":
                    reviewDateObject = datetime.strptime(reviewDateString, "%Y-%m-%d").date()
                    today = datetime.now().date()
                    if reviewDateObject <= today and len(selected_words_lineNumber) < 10:
                        selected_words_lineNumber.append([word, lineNumber, reviewFrequency, reviewDateString])
                elif reviewFrequency == "B":
                    number_burned = number_burned + 1
                total_lines = total_lines + 1

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
    random.shuffle(selected_words)

    percentage_burned = number_burned / total_lines

    return selected_words_lineNumber, selected_words, percentage_burned

def assistant_create_story(selected_words):

    assistant_id = "asst_qXm8leIYM7P33EpQb0m582g7"

    content = f"""
                    Write a story in simple German with maximum 3 sentences.
                    Make sure these words are in the story: {",".join(selected_words)}
                """

    # Thread represents a conversation per user
    # Once this is no longer a beta feature, can consider initiating a thread when the user clicks on Create Story button
    # However this will require a thorough rework of the app and with little upside at the moment
    thread = client.beta.threads.create()

    # Add a message to the thread
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=content
    )

    response = get_response_from_assistant(assistant_id, thread.id)
    return response


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

    # Use the latest Assistants API beta feature here because it allows referencing vocabulary list and
    # is better at following instructions

    # Print story in German
    # response = get_completion_from_messages(messages, model="gpt-4", temperature=temperature)
    # response = response.strip('"')

    response = assistant_create_story(selected_words)

    messages.append(
        {'role': 'assistant',
         'content': response
         }
    )

    return messages, response




def save_to_csv():

    updated_content = []

    with open(file_path, 'r') as file:
        lines = file.readlines()

    # Modify the rows that have updated frequency and review date
    selected_words_lineNumber = session['selected_words_lineNumber']
    rows_to_update = []
    for selected_word_LineNumber in selected_words_lineNumber:
        rows_to_update.append(selected_word_LineNumber[1])

    for i, line in enumerate(lines, start=0):
        if i in rows_to_update:
            updated_line = ""
            for selected_word_LineNumber in selected_words_lineNumber:
                if selected_word_LineNumber[1] == i:
                    updated_line = selected_word_LineNumber[0] + "," + selected_word_LineNumber[2] + ',' + selected_word_LineNumber[3] + "\n"
            updated_content.append(updated_line)
            #print(updated_line)
        else:
            updated_content.append(line)

    # Write data to CSV file
    #print(updated_content[0])
    with open(file_path, 'w') as file:
        file.writelines(updated_content)

@app.route('/')
def index():
    # anki(selected_words_lineNumber, wortLines)
    # translate_to_English(messages)
    # save_to_csv(wortLines)
    return render_template('index.html')

def log_datetime():
    now = datetime.now()
    with open('datetime_log.txt', 'a') as log_file:
        log_file.write(now.strftime("%Y-%m-%d %H:%M:%S") + "\n")


def get_last_run_datetime():
    try:
        with open('datetime_log.txt', 'r') as log_file:
            lines = log_file.readlines()
            if lines:
                last_run_datetime = lines[-1].strip()
                return last_run_datetime
    except FileNotFoundError:
        return "No run history available."

@app.route('/germanStory', methods=['POST'])
def germanStory():

    selected_words_lineNumber, selected_words, percentage_burned = chooseSelectedWords()
    messages, response = create_story(selected_words, temperature=percentage_burned)

    session['selected_words_position'] = 0
    session['selected_words_lineNumber'] = selected_words_lineNumber
    session['messages'] = messages
    session['germanStory'] = response

    # Get the last run datetime from the log file
    last_run_datetime = get_last_run_datetime()

    result_data = {
        'germanStoryString': response,
        'percentageBurned': percentage_burned * 100,
        'lastRunDateTime': last_run_datetime
    }

    # Save current run datetime in log file
    log_datetime()

    return render_template('germanStory.html', result = result_data)

@app.route('/anki', methods=['POST','GET'])
def anki():

        selected_words_lineNumber = session['selected_words_lineNumber']
        selected_words_position = session['selected_words_position']

        wort = selected_words_lineNumber[selected_words_position][0]
        session['anki_word'] = wort

        result_data = {
            'wort': wort,
            'number': selected_words_position + 1
        }

        return render_template('anki.html', result = result_data)


@app.route('/ankiSentence')
def ankiSentence():
    wort = session['anki_word']

    assistant_id = "asst_qXm8leIYM7P33EpQb0m582g7"

    content = "Write 1 sentence in German that has this word: " + wort

    # Thread represents a conversation per user
    thread = client.beta.threads.create()

    # Add a message to the thread
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=content
    )

    response = get_response_from_assistant(assistant_id, thread.id)

    session['anki_sentence'] = response

    return response

@app.route('/ankiTranslate', methods=['POST'])
def anki_translate():

    selected_words_lineNumber = session['selected_words_lineNumber']
    selected_words_position = session['selected_words_position']

    wort = selected_words_lineNumber[selected_words_position][0]
    lineNumber = selected_words_lineNumber[selected_words_position][1]
    final_word = 0

    if (selected_words_position + 1) == len(selected_words_lineNumber):
        final_word = 1

    result_data = {
        'translation': '',
        'frequency1': '',
        'frequency2': '',
        'frequency1_display': '',
        'frequency2_display': '',
        'final_word': final_word
    }

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
    result_data['translation'] = response

    # Request for next Frequency
    currentFrequency = selected_words_lineNumber[selected_words_position][2]
    if currentFrequency == "" or currentFrequency == "T":
        result_data['frequency1'] = 'T'
        result_data['frequency2'] = 'W'
    elif currentFrequency == "W":
        result_data['frequency1'] = 'T'
        result_data['frequency2'] = 'M'
    elif currentFrequency == "M":
        result_data['frequency1'] = 'T'
        result_data['frequency2'] = '3M'
    elif currentFrequency == "3M":
        result_data['frequency1'] = 'T'
        result_data['frequency2'] = 'B'
    elif currentFrequency == "B":
        result_data['frequency1'] = 'B'
        result_data['frequency2'] = 'B'

    def get_display_frequency(frequency_code):
        if frequency_code == 'T':
            return 'Tomorrow'
        elif frequency_code == 'W':
            return 'Week'
        elif frequency_code == 'M':
            return 'Month'
        elif frequency_code == '3M':
            return '3 Months'
        elif frequency_code == 'B':
            return 'Burned'
        else:
            return 'Unknown'

    result_data['frequency1_display'] = get_display_frequency(result_data['frequency1'])
    result_data['frequency2_display'] = get_display_frequency(result_data['frequency2'])

    return render_template('ankiTranslate.html', result=result_data)

@app.route('/ankiSentenceEnglish')
def ankiSentenceEnglish():
   anki_sentence = session['anki_sentence']
   anki_sentence_english = translateToEnglish(anki_sentence)
   return anki_sentence_english

def translateToEnglish(germanText):
    messages = [
        {'role': 'system',
         'content': f"""
                    You are given text in German. Translate it to English. 
                 """
         },
        {'role': 'user',
         'content': germanText
         }
    ]

    englishVersion = get_completion_from_messages(messages, max_tokens=100)

    return englishVersion

def correctSpellingGrammar(germanText):
    messages = [
        {'role': 'system',
         'content': f"""
                        Read this German text and fix any spelling and grammar errors.
                        If there are no errors then respond back with the same German text.
                     """
         },
        {'role': 'user',
         'content': germanText
         }
    ]
    # print("correctSpellingGrammar:")
    # print(messages)
    correctSpellingGrammarVersion = get_completion_from_messages(messages, model="gpt-4", max_tokens=500)
    # print(correctSpellingGrammarVersion)

    return correctSpellingGrammarVersion

@app.route('/englishTranslation', methods=['POST','GET'])
def englishTranslation():
    messages = session['messages']
    germanStory = session['germanStory']

    messages.append(
        {'role': 'user',
         'content': 'Translate this German Story to English.'
         }
    )

    # Print story in English
    response = get_completion_from_messages(messages)

    result_data = {
        'germanStory': germanStory,
        'englishStory': response
    }

    return render_template('englishTranslation.html', result=result_data)

@app.route('/ankiRecord', methods=['POST'])
def updateReviewDate():
    # Based on next Frequency update the review date
    today = datetime.now().date()
    nextReviewDate = ""

    freq_input = request.form['frequency']

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

    selected_words_lineNumber = session['selected_words_lineNumber']
    selected_words_position = session['selected_words_position']

    selected_words_lineNumber[selected_words_position][2] = freq_input
    selected_words_lineNumber[selected_words_position][3] = nextReviewDate.strftime("%Y-%m-%d")

    session['selected_words_position'] = selected_words_position + 1
    session['selected_words_lineNumber'] = selected_words_lineNumber

    if (selected_words_position + 1) < len(selected_words_lineNumber):
        return redirect(url_for('anki', _external=False))
        # return redirect('/App/GermanFriendOnline/anki')
    else:
        # Update the Wortlist file with updated frequency and date
        save_to_csv()
        # Show the English Translation
        return redirect(url_for('englishTranslation', _external=False))
        # return redirect('/App/GermanFriendOnline/englishTranslation')

@app.route('/germanConversation', methods=['POST'])
def germanConversation():
    # Save current run datetime in log file
    log_datetime()
    return render_template('germanConversation.html')

@app.route('/germanScenario', methods=['POST'])
def germanScenario():
    result_data = []

    scenarioText = request.form['scenarioText']

    # scenarioText = scenarioText + ". You will always respond in German. Only use words that are from the Goethe-Zertifikat A1 vocabulary list."

    # Start a CharGPT conversation with the scenarioText as the system message
    # conversationMessages = [
    #     {'role': 'system',
    #      'content': scenarioText
    #      }
    # ]

    # session['conversationMessages'] = conversationMessages

    chat_thread = client.beta.threads.create()

    message = client.beta.threads.messages.create(
        thread_id=chat_thread.id,
        role="user",
        content=scenarioText
    )

    session['chat_thread_id'] = chat_thread.id

    return render_template('iSay.html', result=result_data)

@app.route('/iSayDynamic', methods=['POST'])
def iSayDynamic():

    assistant_id = "asst_SMi97meJ2ArZr2iMwNSQ2Hy0"

    session['iSayText'] = request.form['iSayText']
    iSayText = request.form['iSayText']

    # conversationMessages = session['conversationMessages']

    """
    conversationMessages.append(
        {'role': 'user',
         'content': iSayText
         }
    )
    """

    chat_thread_id = session['chat_thread_id']

    isay_message = client.beta.threads.messages.create(
        thread_id=chat_thread_id,
        role="user",
        content=iSayText
    )

    # youSayText = get_completion_from_messages(conversationMessages, max_tokens=100)

    youSayText = get_response_from_assistant(assistant_id, chat_thread_id)

    session['youSayText'] = youSayText
    """
    conversationMessages.append(
        {'role': 'assistant',
         'content': youSayText
         }
    )
    session['conversationMessages'] = conversationMessages
    """

    result_data = {
        'youSayText': youSayText,
        'iSayText': iSayText
    }

    return render_template('youSayDynamic.html', result=result_data)

@app.route('/conversationEnglishTranslation')
def conversationEnglishTranslation():
    youSayText = session['youSayText']
    youSayTextEnglish = translateToEnglish(youSayText)
    return youSayTextEnglish

@app.route('/conversationSpellGrammarCheck')
def conversationSpellGrammarCheck():
    iSayText = session['iSayText']
    iSayTextReviewed = correctSpellingGrammar(iSayText)
    return iSayTextReviewed



@app.route('/youSay', methods=['POST'])
def youSay():
    return render_template('iSay.html')

if __name__ == '__main__':
    app.run(debug=False, port=5000)