import requests
import base64
from getpass import getpass
import os
from bs4 import BeautifulSoup
import sys
import json
import re

BB_BASE = 'https://blackboard.ru.nl{}'

BB_COURSE_URL = BB_BASE.format(
    '/webapps/blackboard/execute/modulepage/view?course_id=_{course_id}_1&'
    'cmp_tab_id=_225350_1'
)

BB_LOGIN_URL = BB_BASE.format('/webapps/login/')

BB_ASSIGNMENTS_URL = BB_BASE.format(
    '/webapps/gradebook/do/instructor/downloadGradebook?dispatch=viewDownload'
    'Options&course_id=_{course_id}_1'
)

BB_DOWNLOAD_URL = BB_BASE.format(
    '/webapps/gradebook/do/instructor/downloadAssignment'
)

BB_PREDOWNLOAD_URL = (
    BB_DOWNLOAD_URL + '?outcome_definition_id={ass_id}&showAll=true&'
    'course_id=_{course_id}_1&startIndex=0'
)


# Blame Blackboard
# Source: https://blackboard.ru.nl/javascript/md5.js?v=9.1.201410.160373-3
def b64_unicode(string):
    if len(string) % 2 != 0:
        string += chr(0)
    binarray = [(ord(string[2 * i + 1]) << 16) | ord(string[2 * i]) for i in
                range(len(string) / 2)]

    tab = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    b64pad = "="
    result = ""
    for i in range(0, len(binarray) * 4, 3):
        i0 = 0 if (i >> 2) >= len(binarray) else binarray[i >> 2]
        i1 = 0 if (i + 1 >> 2) >= len(binarray) else binarray[i + 1 >> 2]
        i2 = 0 if (i + 2 >> 2) >= len(binarray) else binarray[i + 2 >> 2]

        triplet = ((((i0 >> 8 * (i % 4)) & 0xFF) << 16) |
                   (((i1 >> 8 * ((i + 1) % 4)) & 0xFF) << 8) |
                   ((i2 >> 8 * ((i + 2) % 4)) & 0xFF))
        for j in range(4):
            if i * 8 + j * 6 > len(binarray) * 32:
                result += b64pad
            else:
                result += tab[(triplet >> 6 * (3 - j)) & 0x3F]
    return result


def login(session, user_id):
    password = getpass('Please enter password for {}: '.format(user_id))
    encoded_pass = base64.b64encode(password)
    encoded_uni_pass = b64_unicode(password)

    login_data = {
        'action': 'login',
        'auth_type': '',
        'encoded_pw': encoded_pass,
        'encoded_pw_unicode': encoded_uni_pass,
        'login': 'Login',
        'new_loc': '',
        'one_time_token': '',
        'password': '',
        'remote-user': '',
        'user_id': user_id
    }

    r = session.post(BB_LOGIN_URL, login_data)

    return 'cookie_name' in r.content


def get_new_course(session):
    print 'Adding new course...'
    course_id = raw_input('Please enter a course id: ')
    r = session.get(BB_COURSE_URL.format(course_id=course_id))

    if 'Breadcrumb must have a title' in r.content:
        print 'Course does not exist'
        sys.exit()

    soup = BeautifulSoup(r.content, 'lxml')
    desc = soup.find('a', id='courseMenu_link').text

    match = re.match('^[0-9]{4} (.+) \(.*\)$', desc)
    name = match.group(1)

    print 'Successfully added course "{}"'.format(name)
    return course_id, name


def get_assignments(session, course_id):
    print 'Retrieving assignments...'
    response = session.get(BB_ASSIGNMENTS_URL.format(course_id=course_id))

    soup = BeautifulSoup(response.text, 'lxml')
    options = soup.find('select', id='item').find_all('option')
    assignments = {}
    for option in options:
        if 'Total' not in option.text:
            key = option['value'].split('_')[1]
            assignments[key] = option.text
    return assignments


def get_choice(dictionary):
    keys = sorted(dictionary.keys())
    for i in range(len(dictionary)):
        print '{}:\t{}'.format(i + 1, dictionary[keys[i]])

    choice = int(raw_input('>> '))
    if choice < 1 or choice > len(dictionary):
        print 'Invalid choice.'
        sys.exit()

    return keys[choice - 1], dictionary[keys[choice - 1]]


def download_assignment(session, course_id, assignment_id, assignment_name):
    print 'Preparing download...'
    response = session.get(BB_PREDOWNLOAD_URL.format(ass_id=assignment_id,
                                                     course_id=course_id))

    soup = BeautifulSoup(response.content, 'lxml')
    inputs = soup.find('form', attrs={'name': 'mainForm'}).find_all('input')

    post_data = []
    for el in inputs:
        post_data.append((el['name'], el['value']))

    print 'Downloading assignment...'
    response = session.post(BB_DOWNLOAD_URL, post_data)
    soup = BeautifulSoup(response.content, 'lxml')
    location = soup.find('div', id='bbNG.receiptTag.content').find('a')['href']

    r = session.get('https://blackboard.ru.nl{}'.format(location), stream=True)
    with open('{}.zip'.format(assignment_name), 'wb') as zip_file:
        zip_file.write(r.content)

    print 'Download complete!'


if os.path.exists('config.json'):
    with open('config.json') as config_file:
        config = json.load(config_file)
else:
    print 'No config file found!'
    user = raw_input('Please enter your student number: ')
    config = {'user_id': user, 'courses': {'new_course': 'Add new course.'}}
    with open('config.json', 'w') as config_file:
        json.dump(config, config_file)

with requests.Session() as s:
    if not login(s, config['user_id']):
        print 'Login failed.'
        sys.exit()

    print 'For which course would you like to download an assignment?'
    course = get_choice(config['courses'])[0]

    if course == 'new_course':
        course, course_name = get_new_course(s)
        config['courses'][course] = course_name
        with open('config.json', 'w') as config_file:
            json.dump(config, config_file, sort_keys=True, indent=4)

    assignment_choices = get_assignments(s, course)
    print 'Which assignment would you like to download?'
    ass_id, ass_name = get_choice(assignment_choices)
    download_assignment(s, course, ass_id, ass_name)
