from app import app, db, celery
from app.models import Hall, Manager, Meal, Item, Nutrition

from celery.schedules import crontab

import os
import requests
import json
import datetime
import re
from bs4 import BeautifulSoup
import time
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException

DATE_FMT = '%A, %B %d, %Y'
WAIT_PERIOD = 10
MENU_FILE = 'menus.json'
FASTTRACK_NAME_OVERRIDES = {
    'Franklin': 'Benjamin Franklin',
    'Stiles': 'Ezra Stiles',
}
NICKNAMES = {
    **{name: nickname for nickname, name in FASTTRACK_NAME_OVERRIDES.items()},
    'Grace Hopper': 'Hopper',
    'Jonathan Edwards': 'JE',
    'Pauli Murray': 'Murray',
    'Timothy Dwight': 'TD',
}
JAMIX_HALL_NAMES = {
    **FASTTRACK_NAME_OVERRIDES,
    'Murray': 'Pauli Murray',
    'Hopper': 'Grace Hopper',
    'ESM': 'Ezra Stiles/Morse',
    'JE': 'Jonathan Edwards',
}
HALL_IDS = {
    'Berkeley': 'BK',
    'Branford': 'BR',
    'Davenport': 'DC',
    'Franklin': 'BF',
    'Grace Hopper': 'GH',
    'Jonathan Edwards': 'JE',
    'Morse': 'MC',
    'Pauli Murray': 'MY',
    'Pierson': 'PC',
    'Saybrook': 'SY',
    'Silliman': 'SM',
    'Stiles': 'ES',
    'Timothy Dwight': 'TD',
    'Trumbull': 'TC',
}
COURSE_NAME_OVERRIDES = {
    'Yale Bakery Dessert': 'Dessert',
}

driver = None

def create_driver():
    # TODO: using globals is bad practice.
    global driver

    ops = webdriver.ChromeOptions()
    ops.add_argument('--disable-gpu')
    ops.add_argument('--no-sandbox')
    GOOGLE_CHROME_PATH = os.environ.get('GOOGLE_CHROME_PATH')
    if GOOGLE_CHROME_PATH:
        ops.binary_location = GOOGLE_CHROME_PATH
    CHROMEDRIVER_PATH = os.environ.get('CHROMEDRIVER_PATH', '/usr/local/bin/chromedriver')
    driver = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, chrome_options=ops)
    driver.maximize_window()
    driver.implicitly_wait(WAIT_PERIOD)


def read_nutrition_facts(raw):
    nutrition = Nutrition(
        serving_size=raw.pop('Serving Size', None),
    )
    for key in raw:
        snaked_key = key.lower().replace(' ', '_')
        setattr(nutrition, snaked_key, raw[key]['amount'])
        setattr(nutrition, snaked_key + '_pdv', raw[key].get('percent_daily_value'))
    return nutrition


def scrape_fasttrack():
    # Reach out to old FastTrack-based dining API,
    # which still provides non-menu data
    FASTTRACK_ROOT = 'https://www.yaledining.org/fasttrack/'
    params = {
        'version': 3,
    }
    r = requests.get(FASTTRACK_ROOT + 'locations.cfm', params=params)
    data = r.json()
    # Restructure data into a list of dictionaries for easier manipulation
    data = [
        {data['COLUMNS'][index]: entry[index] for index in range(len(entry))}
        for entry in data['DATA']
    ]
    for raw in data:
        if raw['TYPE'] != 'Residential':
            continue
        # We currently don't use this ID as it is relatively meaningless and using the building code is clearer
        #hall_id = int(raw['ID_LOCATION'])
        name = raw['DININGLOCATIONNAME']
        hall_id = HALL_IDS[name]
        hall = Hall.query.get(hall_id)
        if hall is None:
            hall = Hall(id=hall_id)
        # TODO: I can't figure out what this is for, so just omit it for now.
        #hall.code = int(raw['LOCATIONCODE']),
        # Get custom name override, falling back to provided name where applicable
        hall.name = FASTTRACK_NAME_OVERRIDES.get(name, name)
        hall.nickname = NICKNAMES.get(hall.name, hall.name)
        hall.occupancy = raw['CAPACITY']
        hall.open = not bool(raw['ISCLOSED'])
        hall.address = raw['ADDRESS']
        hall.phone = raw['PHONE']
        # Ignore manager fields as they're now outdated.
        print('Parsing ' + hall.name)
        geolocation = raw.get('GEOLOCATION')
        if geolocation is not None:
            hall.latitude, hall.longitude = [float(coordinate) for coordinate in geolocation.split(',')]
        db.session.add(hall)
    db.session.commit()
    print('Done reading FastTrack data.')


def scrape_managers():
    print('Scraping managers.')
    ROOT = 'https://hospitality.yale.edu/residential-dining/'
    halls = Hall.query.all()
    HEADER_RE = re.compile(r'Management Team')
    Manager.query.delete()
    for hall in halls:
        slug = hall.name.lower().replace(' ', '-')
        custom_slugs = {
            'franklin': 'benjamin-franklin',
            'stiles': 'ezra-stiles',
        }
        if slug in custom_slugs:
            slug = custom_slugs[slug]
        print(slug)
        r = requests.get(ROOT + slug)
        soup = BeautifulSoup(r.text, 'html.parser')
        h2 = soup.find('h2', text=HEADER_RE)
        ul = h2.find_next()
        if ul.name == 'p':
            to_scan = [ul]
        elif ul.name == 'ul':
            to_scan = ul.find_all('li')
        for li in to_scan:
            contents = li.contents
            manager = Manager()
            if len(contents) == 1:
                # The name is not a link, so no email is available
                manager.name, manager.position = contents[0].split(', ')
            elif len(contents) == 2:
                manager.name = contents[0].text
                manager.email = contents[0]['href'].replace('mailto:', '')
                manager.position = contents[1].lstrip(', ').replace('/ ', '/').replace(' /', '/')
            db.session.add(manager)
            manager.hall = hall
            print('Name: ' + manager.name)
            print('Email: %s' % manager.email)
            print('Position: %s' % manager.position)
    db.session.commit()


####################################
# JAMIX Selenium Web Parsing Section

###################################
# Functions for getting UI elements


def get_header_text():
    return driver.find_element_by_class_name('label-main-caption').text


def get_subheader_text():
    return driver.find_element_by_class_name('label-sub-caption').text


def get_tabs():
    driver.implicitly_wait(1)
    tabs_bar = driver.find_elements_by_class_name('v-tabsheet')
    driver.implicitly_wait(WAIT_PERIOD)
    if len(tabs_bar) == 0:
        return []
    return tabs_bar[0].find_elements_by_class_name('v-caption')


def get_courses():
    courses = driver.find_element_by_css_selector('div.v-verticallayout.v-layout.menu-sub-view').find_elements_by_class_name('v-button')
    print('Found %d courses this time.' % len(courses))
    return courses


def get_ingredients_and_nutrition_buttons():
    return driver.find_elements_by_css_selector('.v-button.v-widget.multiline.v-button-multiline.selection.v-button-selection.icon-align-right.v-button-icon-align-right.v-has-width')


def get_serving_size():
    text = driver.find_element_by_css_selector('.v-panel-content .v-panel-captionwrap').text.replace('Nutrition Facts\n', '')
    # Chop off parentheses
    if text[0] == '(' and text[-1] == ')':
        text = text[1:-1]
    return text


def get_item_nutrition_buttons():
    return driver.find_elements_by_css_selector('.v-button.nutrition')


def click_back():
    sleep()
    driver.find_element_by_css_selector('.button-navigation--previous .v-button').click()
    sleep()


def click_previous_date():
    previous_date_button = driver.find_element_by_class_name('button-date-selection--previous')
    previous_date_button.click()
    sleep()


def click_next_date():
    next_date_button = driver.find_element_by_class_name('button-date-selection--next')
    next_date_button.click()
    sleep()


def clean_hall_name(hall_name):
    hall_name = hall_name.replace(', Residential', '')
    if hall_name in JAMIX_HALL_NAMES:
        hall_name = JAMIX_HALL_NAMES[hall_name]
    return hall_name

######################
# Other util functions


def sleep():
    time.sleep(0.5)


def day_after(date):
    """
    Given a date, return the next day in that format.
    """
    fut = date + datetime.timedelta(days=1)
    return fut.strftime(DATE_FMT)


def seek_date(target_date) -> bool:
    """
    Seek toward a target date.
    :return: whether the date has been reached.
    """
    target_date = datetime.datetime.strptime(target_date, DATE_FMT)
    while True:
        current_date = get_subheader_text()
        current_date = datetime.datetime.strptime(current_date, DATE_FMT)
        if current_date == target_date:
            break
        if current_date < target_date:
            click_next_date()
        else:
            click_previous_date()
        sleep()


################################
# Parsing process functions


def seek_start(start_date=None):
    # Go to earliest available date or requested date
    while True:
        panels = driver.find_elements_by_class_name('v-panel-content')
        if len(panels) == 1:
            # The only panel is the no menus error message
            click_next_date()
            break
        click_previous_date()
        sleep()
        sleep()


def parse_ingredients():
    """
    Parse ingredients page that's on the screen.
    """
    sleep()
    ingredients = {}
    rows = driver.find_element_by_css_selector('.v-verticallayout.v-layout.v-vertical.v-widget.v-has-width.v-margin-top.v-margin-right.v-margin-bottom.v-margin-left .v-verticallayout').find_elements_by_xpath('./div[contains(@class, "v-slot")]')
    print('Found %d rows of ingredients data.' % len(rows))
    rows_processed = 0
    current_title = None
    looking_for = 'title'
    while rows_processed < len(rows):
        if looking_for == 'title':
            slots = rows[rows_processed].find_elements_by_css_selector('.v-label')
            current_title = slots[0].text
            ingredients[current_title] = {
                'diets': slots[1].text,
            }
            looking_for = 'ingredients'
            rows_processed += 1
        elif looking_for == 'ingredients':
            ingredients[current_title]['ingredients'] = rows[rows_processed].text
            looking_for = 'allergens'
            rows_processed += 1
        elif looking_for == 'allergens':
            text = rows[rows_processed].text
            if text.startswith('Allergens: '):
                ingredients[current_title]['allergens'] = text.replace('Allergens: ', '')
                rows_processed += 1
            looking_for = 'title'
    return ingredients


def parse_nutrition_facts():
    """
    Parse a visible nutrition facts pane, whether for a full course or an individual item.
    """
    nutrition_facts = {
        'Serving Size': get_serving_size(),
    }
    lists = driver.find_elements_by_css_selector('.v-panel-content ul')
    if len(lists) != 2:
        print('Warning: more than 2 uls found on nutrition facts page.')
    # The nutrition facts table is made with two uls, the first of which has the ingredient name and amount of it,
    # and the second of which has the daily values.
    # The elements in the left side list
    llist = BeautifulSoup(lists[0].get_attribute('innerHTML'), 'html.parser').findChildren(recursive=False)
    # The elements in the right side list
    rlist = BeautifulSoup(lists[1].get_attribute('innerHTML'), 'html.parser').findChildren(recursive=False)
    for lside, rside in zip(llist, rlist):
        # Skip if we're on an empty row
        if lside.text.strip() == '':
            continue
        spans = lside.find_all('span')
        ingredient = spans[0].text.lstrip('- ')
        amount = spans[1].text
        if ingredient == 'Calories':
            amount = float(amount.replace(' kcal', ''))
        nutrition_facts[ingredient] = {
            'amount': amount,
        }

        rtext = rside.text.strip(' %')
        if rtext:
            nutrition_facts[ingredient]['percent_daily_value'] = int(rtext)
    return nutrition_facts


def parse_nutrition_facts_course():
    """
    Parse nutrition facts for an entire course.
    """
    nutrition_facts = {
        'course': parse_nutrition_facts(),
        'items': {},
    }
    items = get_item_nutrition_buttons()
    if items:
        items_processed = 0
        while items_processed < len(items):
            # TODO: stop this from running twice on the first go. And same with other such constructs in this file.
            items = get_item_nutrition_buttons()
            item_name = items[items_processed].text
            items[items_processed].click()
            sleep()

            nutrition_facts['items'][item_name] = parse_nutrition_facts()

            click_back()

            items_processed += 1
    return nutrition_facts


def parse_course():
    """
    Parse course that has been opened on the screen (i.e. Ingredients and Nutrition Facts buttons are showing).
    """
    course_name = get_header_text()
    course_name = COURSE_NAME_OVERRIDES.get(course_name, course_name)
    course = {
        'name': course_name,
    }
    # Grab and parse Ingredients page
    in_buttons = get_ingredients_and_nutrition_buttons()
    in_buttons[0].click()
    sleep()

    course['ingredients'] = parse_ingredients()

    click_back()
    # Do again to reattach to the list
    in_buttons = get_ingredients_and_nutrition_buttons()
    in_buttons[1].click()
    sleep()

    course['nutrition_facts'] = parse_nutrition_facts_course()

    click_back()  # to Ingredients/Nutrition Facts Selection pane
    sleep()
    return course


def parse_meal(name):
    """
    Parse the meal currently on the screen, whether or not it was accessed via a tab.
    """
    meal = {
        'name': name,
        'courses': [],
    }
    courses = get_courses()
    courses_processed = 0
    while courses_processed < len(courses):
        courses = get_courses()
        courses[courses_processed].click()
        sleep()

        meal['courses'].append(parse_course())

        click_back()  # to main page/meal
        sleep()
        courses_processed += 1
    return meal


if os.path.exists(MENU_FILE):
    with open(MENU_FILE, 'r') as f:
        menus = json.load(f)
else:
    menus = {}


def parse_right(hall_name):
    print('Parsing ' + hall_name)

    # Cycle through dates, collecting data
    while True:
        today_menu = {
            'date': get_subheader_text(),
            'meals': [],
        }

        print('Parsing date %s...' % today_menu['date'])

        panels = driver.find_elements_by_class_name('v-panel-content')
        if len(panels) == 1:
            break
        sleep()
        tabs = get_tabs()
        has_tabs = (len(tabs) > 0)
        if has_tabs:
            print('Found %d tabs on this page.' % len(tabs))
            tabs_processed = 0
            while tabs_processed < len(tabs):
                # TODO: remove repetition
                tabs = get_tabs()
                sleep()
                tabs[tabs_processed].click()
                sleep()
                meal_name = tabs[tabs_processed].text

                today_menu['meals'].append(parse_meal(meal_name))

                tabs_processed += 1
        else:
            print('No tabs are available. Parsing single meal.')
            # TODO: does this default hold?
            today_menu['meals'].append(parse_meal('Breakfast'))

        menus[hall_name].append(today_menu)
        with open(MENU_FILE, 'w') as f:
            json.dump(menus, f)
        click_next_date()
        sleep()

    return True


def get_last_day(hall_name):
    # Handle multi-hall names
    # TODO this is messy
    # .split(' and ')[0].split(' & ')[0]
    if hall_name == 'ESM':
        hall_name = 'Ezra Stiles'
    hall_name = hall_name.split('/')[0]
    hall_name = clean_hall_name(hall_name)
    print(hall_name)
    hall = Hall.query.filter_by(name=hall_name).first()
    print(hall)
    last_meal = Meal.query.filter_by(hall_id=hall.id).order_by(Meal.date.desc()).first()
    last_day = last_meal.date if last_meal else None
    if hall_name in menus and menus[hall_name]:
        last_cached_day = datetime.datetime.strptime(menus[hall_name][-1]['date'], DATE_FMT).date()
        # Make lexicographic comparison
        if last_day is None or last_cached_day > last_day:
            last_day = last_cached_day
    return last_day


def parse(hall_jamix_id):
    finished = False
    while not finished:
        driver.get('https://usa.jamix.cloud/menu/app?anro=97939&k=%d' % hall_jamix_id)
        sleep()
        hall_name = get_header_text()
        hall_name = clean_hall_name(hall_name)
        if hall_name not in menus:
            menus[hall_name] = []
        # If there's already some days in the list, then go to the next day.
        # Otherwise, go all the way to the start.
        # TODO: in theory, if we didn't run the scraper for a really long time, this could take us
        # back to a time where there's no data, and the parser will think it's finished with this hall.
        # Hopefully we'll run often enough that this won't happen, but it would be good to be sure.
        last_day = get_last_day(hall_name)
        if last_day:
            seek_date(day_after(last_day))
        else:
            # TEMPORARY
            seek_date(datetime.date.today() + datetime.timedelta(days=5))
            seek_start()

        try:
            finished = parse_right(hall_name)
        except (ElementClickInterceptedException, ElementNotInteractableException, IndexError) as e:
            print('Squashing error...')
            print(e)
    return hall_name, menus[hall_name]


def parse_hall(hall_name):
    print('Parsing hall ' + hall_name)
    for day_d in menus[hall_name]:
        date = datetime.datetime.strptime(day_d['date'], DATE_FMT).date()
        print('Parsing day ' + day_d['date'])
        for meal_d in day_d['meals']:
            meal_name = meal_d['name']
            print('Parsing meal ' + meal_name)
            if meal_name == 'Breakfast':
                start_time = '08:00'
                end_time = '10:30'
            elif meal_name == 'Lunch':
                start_time = '11:30'
                end_time = '14:00'
            elif meal_name == 'Dinner':
                start_time = '17:00'
                end_time = '19:30'
            else:
                start_time = None
                end_time = None
            meal = Meal(
                name=meal_name,
                date=date,
                start_time=start_time,
                end_time=end_time,
            )
            meal.hall = Hall.query.filter_by(name=hall_name).first()
            for course_d in meal_d['courses']:
                course_name = course_d['name']
                print('Parsing course ' + course_name)
                # Note that both ingredients and nutrition_facts['items'] are dictionaries,
                # with the keys being the names of the items.
                ingredients = course_d['ingredients']
                nutrition_facts = course_d['nutrition_facts']
                for item_name in ingredients:
                    print('Parsing item ' + item_name)
                    item = Item(
                        name=item_name.replace('`', '\''),
                        ingredients=ingredients[item_name]['ingredients'],
                        course=course_name,
                    )
                    diets = ingredients[item_name]['diets'].split(', ')
                    item.animal_products = not ('V' in diets)
                    item.meat = not ('VG' in diets)
                    item.gluten = not ('GF' in diets)
                    allergens = ingredients[item_name].get('allergens')
                    if allergens:
                        allergens = allergens.split(', ')
                        for allergen in allergens:
                            setattr(item, allergen.lower(), True)

                    # TODO: this should always be present, but handle its absence in case the scraper broke
                    if nutrition_facts['items'].get(item_name):
                        # Read nutrition facts
                        # TODO: 'nutrition' or 'nutrition facts'?
                        nutrition = read_nutrition_facts(nutrition_facts['items'][item_name])
                        db.session.add(nutrition)
                        item.nutrition = nutrition
                    item.meal = meal
                    db.session.add(item)
                #course_nutrition = read_nutrition_facts(nutrition_facts['course'])
                #db.session.add(course_nutrition)
            db.session.add(meal)
    db.session.commit()


def scrape_jamix():
    print('Reading JAMIX menu data.')
    create_driver()

    # Iterate through halls
    for hall_jamix_id in range(1, 11 + 1):
        hall_name, hall = parse(hall_jamix_id)
        # Separate multi-hall menus
        # TODO: should we do this at request time?
        if '/' in hall_name:
            value = menus.pop(hall_name)
            hall_name_a, hall_name_b = hall_name.split('/')
            hall_name_a = clean_hall_name(hall_name_a)
            hall_name_b = clean_hall_name(hall_name_b)
            menus[hall_name_a] = value
            menus[hall_name_b] = value
            parse_hall(hall_name_a)
            parse_hall(hall_name_b)
        else:
            parse_hall(hall_name)

    db.session.commit()
    print('Done.')


@celery.task
def scrape(fasttrack_only=False):
    scrape_fasttrack()
    if not fasttrack_only:
        scrape_managers()
        scrape_jamix()


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(60, scrape.s(fasttrack_only=True), name='FastTrack scrape')
    sender.add_periodic_task(
        crontab(minute=0),
        scrape.s(fasttrack_only=False),
        name='Full scrape'
    )
