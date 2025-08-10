from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_session import Session
import openai
import os
import random
from datetime import datetime, timedelta
import json
import unicodedata
from threading import Thread
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.getenv('FLASK_SESSION_SECRET_KEY')

# Use server-side session storage
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session_data')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

# Store background results (use Redis or DB in production)
story_results = {}  # Dict to hold story by session ID or custom token

# ------------------------------------------------------------------------------
# 1) constants and helper
# ------------------------------------------------------------------------------
DEFAULT_WORTLIST_FILE = "A1Wortlist.csv"

# replace these placeholders with your actual A2 assistant IDs:
ASSISTANT_IDS_ANKI = {
    "A1Wortlist.csv": "asst_qXm8leIYM7P33EpQb0m582g7",
    "A2Wortlist.csv": "asst_tops2pTTY9Db4Nc7qkgNXULq"
}
ASSISTANT_IDS_CONVERSATION = {
    "A1Wortlist.csv": "asst_SMi97meJ2ArZr2iMwNSQ2Hy0",
    "A2Wortlist.csv": "asst_tops2pTTY9Db4Nc7qkgNXULq"
}

def get_current_wortlist_file():
    # fall back to default if none selected
    print(f"Using Wortlist: {session.get('wortlist_file', DEFAULT_WORTLIST_FILE)}")
    return session.get("wortlist_file", DEFAULT_WORTLIST_FILE)

def generate_story_background(session_key, wortlist_file, scenario_text):
    burned_words = get_burned_words(wortlist_file)
    if not burned_words:
        story_results[session_key] = {
            'german': "No burned words available yet. Please review and burn more words first.",
            'english': "No burned words available yet. Please review and burn more words first."
        }
    else:
        prompt = f"""
                1. Write a short story in German about this scenario: {scenario_text}
                2. Write this short story in German primarily using the following Burned words:\n{', '.join(burned_words)}\n\n
                3. Review the short story to confirm that for Nouns or Verbs or Adjectives, only the words in the Burned words list is used
                4. If you find Nouns, Verbs, Adjectives in the short story that are not in the Burned words list, remove them and rewrite that section of the story to use Burned words.
                5. Ensure the German story is interesting and follows the user's scenario.
                6. The output should only be the story.
                """
        messages = [
            {'role': 'system', 'content': 'You are a helpful language teacher.'},
            {'role': 'user', 'content': prompt}
        ]

        try:
            german_story = get_completion_from_messages(messages, model="o4-mini", temperature=0.2, max_tokens=10000)
            messages.append({'role': 'assistant', 'content': german_story})
            messages.append({'role': 'user', 'content': 'Translate this German story to English.'})
            english_story = get_completion_from_messages(messages, model="o4-mini", max_tokens=10000)
            story_results[session_key] = {
                'status': 'done',
                'german': german_story.strip(),
                'english': english_story.strip()
            }
        except Exception as e:
            story_results[session_key] = {
                'status': 'error',
                'german': f"Error generating story: {e}",
                'english': ""
            }

openai.api_key = os.getenv('OPENAI_API_KEY')
# print(openai.api_key)

# If reviewing A1Wortlist, the burned worts are from A1 list
# If reviewing A2Wortlist, then burned worts are from A1 and A2 list.
# Once A2 bunred wort list is large enough (>1000 words) can consider switching to exclusively A2 list.
def get_burned_words(wortlist_file):
    burned_words = []

    file_path = wortlist_file

    files_to_read = []
    if file_path == "A2Wortlist.csv":
        files_to_read = ["A1Wortlist.csv", "A2Wortlist.csv"]
    else:
        files_to_read = [file_path]

    for path in files_to_read:
        try:
            with open(path, 'r') as file:
                for lineNumber, line in enumerate(file):
                    if lineNumber == 0:
                        continue  # Skip header
                    line = line.strip()
                    elements = line.split(',')
                    if len(elements) >= 2:
                        word, frequency = elements[0], elements[1]
                        if frequency == "B":
                            burned_words.append(word)
        except FileNotFoundError:
            print(f"File not found: {path}")

    # Shuffle to ensure random order each time
    random.shuffle(burned_words)

    return burned_words



def get_completion_from_messages(messages, model="gpt-4o-mini", temperature=0.0, max_tokens=500):
    response = openai.chat.completions.create(
        model=model,
        messages=messages,
        max_completion_tokens=max_tokens,
    )
    return response.choices[0].message.content

def get_response_from_assistant(assistant_id, thread_id):
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    while run.status in ["queued", "in_progress"]:
        run = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
    if run.status == "completed":
        thread_messages = openai.beta.threads.messages.list(thread_id=thread_id, order="desc")
        try:
            message_content = thread_messages.data[0].content[0].text
            annotations = message_content.annotations
            for annotation in annotations:
                message_content.value = message_content.value.replace(annotation.text, "")
            response = message_content.value
        except Exception as e:
            response = f"An unexpected error occurred: {e}"
    else:
        # print(run)        
        response = "Error: OpenAI Run Failed"

    return response


# Function to start the assistant run
def start_assistant_run(assistant_id, thread_id):
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )
    return run.id

# Function to check if assistant run is complete and provide the latest status and if complete the latest message as response
def check_assistant_run_completed(thread_id, run_id):
    run = openai.beta.threads.runs.retrieve(
        thread_id=thread_id,
        run_id=run_id
    )

    if run.status == "completed":
        thread_messages = openai.beta.threads.messages.list(thread_id=thread_id, order="desc")
        try:
            message_content = thread_messages.data[0].content[0].text
            annotations = message_content.annotations
            for annotation in annotations:
                message_content.value = message_content.value.replace(annotation.text, "")
            response = message_content.value
        except Exception as e:
            response = f"An unexpected error occurred: {e}"
    else:
        # print(run)
        response = "Error: OpenAI Run Failed"

    return run.status, response


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
    number_week = 0
    number_month = 0
    number_3_month = 0
    number_pending = 0
    number_tomorrow = 0
    total_lines = 0

    file_path = get_current_wortlist_file()

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
                    number_pending = number_pending + 1
                elif reviewFrequency != "B":
                    reviewDateObject = datetime.strptime(reviewDateString, "%Y-%m-%d").date()
                    today = datetime.now().date()
                    if reviewDateObject <= today and len(selected_words_lineNumber) < 10:
                        selected_words_lineNumber.append([word, lineNumber, reviewFrequency, reviewDateString])

                    if reviewFrequency == "W":
                        number_week = number_week + 1
                    elif reviewFrequency == "M":
                        number_month = number_month + 1
                    elif reviewFrequency == "3M":
                        number_3_month = number_3_month + 1
                    elif reviewFrequency == "T":
                        number_tomorrow = number_tomorrow + 1

                elif reviewFrequency == "B":
                    number_burned = number_burned + 1
                total_lines = total_lines + 1

    # print("Number of selected words using reviewDate:", len(selected_words_lineNumber))

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

    # print("Number of selected words after adding random:", len(selected_words_lineNumber))

    # Create a list of selected words
    selected_words = []
    for selected_word_lineNumber in selected_words_lineNumber:
        selected_words.append(selected_word_lineNumber[0])
    random.shuffle(selected_words)

    # percentage_burned = number_burned / total_lines

    return selected_words_lineNumber, selected_words, number_burned, number_week, number_month, number_3_month, number_pending, number_tomorrow

def create_anki_english_sentences(selected_words):

    #assistant_id = "asst_qXm8leIYM7P33EpQb0m582g7"

    # Function to get Anki sentences in 1 go in JSON format. This function starts the run and does not wait for completion
    file_path = get_current_wortlist_file()
    assistant_id = ASSISTANT_IDS_ANKI.get(file_path, ASSISTANT_IDS_ANKI[DEFAULT_WORTLIST_FILE])


    sentences_content = f"""
                1. Write 1 sentence in simple German for each of these words: {",".join(selected_words)}
                2. Provide the response in JSON format where the keys are the words and the values are the corresponding German sentences
                For example: 
                    "Word1": "German sentence for Word1",
                    "Word2": "German sentence for Word2",
                    "Word3": "German sentence for Word3",
                """

    # print("Sentences content" + sentences_content)

    sentences_thread = openai.beta.threads.create()
    session['sentences_thread_id'] = sentences_thread.id

    openai.beta.threads.messages.create(
        thread_id=sentences_thread.id,
        role="user",
        content=sentences_content
    )

    session['sentences_run_id'] = start_assistant_run(assistant_id, sentences_thread.id)

def save_to_csv():

    updated_content = []
    file_path = get_current_wortlist_file()
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


@app.route('/story_scenario', methods=['POST'])
def story_scenario():
    # Save wortlist selection before showing storyScenario.html
    session['wortlist_file'] = request.form.get('wortlist', DEFAULT_WORTLIST_FILE)
    return render_template('storyScenario.html')


@app.route('/stats_and_start_anki', methods=['POST'])
def stats_and_start_anki():

    scenario_text = request.form.get('scenarioText', None)

    selected_words_lineNumber, selected_words, number_burned, number_week, number_month, number_3_month, number_pending, number_tomorrow = chooseSelectedWords()
    percentage_burned = number_burned / (number_burned+number_week+number_month+number_3_month+number_pending)


    create_anki_english_sentences(selected_words)

    session['selected_words_position'] = 0
    session['selected_words_lineNumber'] = selected_words_lineNumber
    session['messages'] = []
    session['germanStory'] = ""

    # Start background story generation
    session_key = session.sid
    story_results[session_key] = {'status': 'in_progress'}
    wortlist_file = session.get("wortlist_file", DEFAULT_WORTLIST_FILE)
    Thread(target=generate_story_background, args=(session_key, wortlist_file, scenario_text)).start()

    # Get the last run datetime from the log file
    last_run_datetime = get_last_run_datetime()

    result_data = {
        'numberBurned': number_burned,
        'numberWeek': number_week,
        'numberMonth': number_month,
        'number3Month': number_3_month,
        'numberPending': number_pending,
        'numberTomorrow': number_tomorrow,
        'lastRunDateTime': last_run_datetime
    }

    # Save current run datetime in log file
    log_datetime()

    return render_template('stats_and_start_anki.html', result = result_data)

@app.route('/ankiSentencesResponse', methods=['POST','GET'])
def ankiSentencesResponse():
    sentences_thread_id = session['sentences_thread_id']
    sentences_run_id = session['sentences_run_id']

    run_status = "in_progress"
    response = "Error"

    # print("sentences generation in progress...")

    while run_status == "queued" or run_status == "in_progress":
        run_status, response = check_assistant_run_completed(sentences_thread_id, sentences_run_id)

    # Print run steps

    run_steps = openai.beta.threads.runs.steps.list(
        thread_id=sentences_thread_id,
        run_id=sentences_run_id
    )
    # print(run_steps)

    # print("run status:" + run_status)
    # print("Sentences response:" + response)

    if run_status == "completed":

        'Clean up the JSON response'
        if 'json' in response:
            response = response.replace('json','',1).strip()
        response = response.strip("```")

        session['anki_sentences'] = response
    else:
        session['anki_sentences'] = "Error"

    return response


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

    # print("anki_word:" + session['anki_word'])

    wort = session['anki_word']
    anki_sentences = session['anki_sentences']
    anki_sentence_for_wort = "Error"
    sentences_data = ""

    try:
        # print("anki_sentences:" + anki_sentences)
        sentences_data = json.loads(anki_sentences)
    except json.JSONDecodeError:
        anki_sentence_for_wort = "Failed to parse JSON. Please check the JSON structure"

    try:
        wort_normalized = unicodedata.normalize('NFC', wort)
        sentences_data_normalized = {unicodedata.normalize('NFC', k): v for k, v in sentences_data.items()}
        anki_sentence_for_wort = sentences_data_normalized.get(wort_normalized)
    except:
        anki_sentence_for_wort = 'Failed to get word. Please check if word is in the JSON string'

    session['anki_sentence'] = anki_sentence_for_wort
    # print("anki_sentence_for_wort:" + anki_sentence_for_wort)

    return anki_sentence_for_wort

@app.route('/ankiTranslate', methods=['POST'])
def anki_translate():

    selected_words_lineNumber = session['selected_words_lineNumber']
    selected_words_position = session['selected_words_position']

    wort = selected_words_lineNumber[selected_words_position][0]
    lineNumber = selected_words_lineNumber[selected_words_position][1]
    final_word = 0
    number = selected_words_position + 1

    if (selected_words_position + 1) == len(selected_words_lineNumber):
        final_word = 1

    result_data = {
        'translation': '',
        'frequency1': '',
        'frequency2': '',
        'frequency1_display': '',
        'frequency2_display': '',
        'final_word': final_word,
        'number': number
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
    correctSpellingGrammarVersion = get_completion_from_messages(messages, model="gpt-4o-mini", max_tokens=500)
    # print(correctSpellingGrammarVersion)

    return correctSpellingGrammarVersion

@app.route('/german_story_status', methods=['GET'])
def german_story_status():
    result = story_results.get(session.sid)
    if not result:
        return jsonify({'status': 'expired'})
    return jsonify({'status': result['status']})

@app.route('/german_story_with_translation', methods=['POST','GET'])
def german_story_with_translation():
    result_data = story_results.get(session.sid, None)
    if not result_data or result_data.get('status') != 'done':
        return render_template('german_story_with_translation.html', result={
            'germanStory': 'The story is still being generated. Even I find this to be hard! This page will refresh shortly.',
            'englishStory': ''
        })

    return render_template('german_story_with_translation.html', result={
        'germanStory': result_data['german'],
        'englishStory': result_data['english']
    })

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
        # return redirect(url_for('anki', _external=False))
        return redirect('anki')
    else:
        # Update the Wortlist file with updated frequency and date
        save_to_csv()
        # Show the German Story with translation
        return redirect('german_story_with_translation')

@app.route('/germanConversation', methods=['POST'])
def germanConversation():
    # Save current run datetime in log file
    session['wortlist_file'] = request.form.get('wortlist', DEFAULT_WORTLIST_FILE)
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

    chat_thread = openai.beta.threads.create()

    message = openai.beta.threads.messages.create(
        thread_id=chat_thread.id,
        role="user",
        content=scenarioText
    )

    session['chat_thread_id'] = chat_thread.id

    return render_template('iSay.html', result=result_data)

@app.route('/iSayDynamic', methods=['POST'])
def iSayDynamic():

    #assistant_id = "asst_SMi97meJ2ArZr2iMwNSQ2Hy0"

    # pick the right assistant for A1 vs A2
    file_path = get_current_wortlist_file()
    assistant_id = ASSISTANT_IDS_CONVERSATION.get(file_path, ASSISTANT_IDS_CONVERSATION[DEFAULT_WORTLIST_FILE])

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

    isay_message = openai.beta.threads.messages.create(
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

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=False, port=5000)
