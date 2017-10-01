# https://api.slack.com/methods

import os
import time
import random
import json
from datetime import datetime
from slackclient import SlackClient
import re

class Lunchbot(object):
    """
    Lunchbot is a Slack bot
    """

    # Slack constants
    CHANNEL = '#lunch'
    BOT_NAME = 'lunchbot'
    SLACK_CLIENT = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
    READ_WEBSOCKET_DELAY = 1 # 1 second delay between reading from firehose

    # Lunchbot constants
    RESTAURANTS = {}
    MESSAGES = {}

    def __init__(self):
        self.read_data()

    def read_data(self):
        """
        Reads data from data file and updates internal constants
        """
        with open('data.json') as data_file:
            data = json.load(data_file)
        self.RESTAURANTS = data['restaurants']
        self.MESSAGES = data['messages']

    def update_data(self):
        data = {}
        data['restaurants'] = self.RESTAURANTS
        data['messages'] = self.MESSAGES
        with open('data.json', 'w') as data_file:
            json.dump(data, data_file)

    def find_restaurant(self, res):
        for restaurant in self.RESTAURANTS:
            if res.lower() == restaurant['name'].lower():
                return restaurant
        return None

    def print_bot_id(self, slack_user):
        """
        Prints ID of given user
        """
        api_call = self.SLACK_CLIENT.api_call('users.list')
        if api_call.get('ok'):
            # retrieve all users so we can find our bot
            users = api_call.get('members')
            for user in users:
                if 'name' in user and user.get('name') == slack_user:
                    print 'Bot ID for \'' + user['name'] + '\' is ' + user.get('id')
                    return user.get('id')
        else:
            print 'Could not find bot user with the name ' + slack_user

    def weighted_choice(self, choices):
        """
        Given a list of tuples where each tuple is of the form
        (item, weight), this function will return a random choice
        taking into account the weight of each item
        """
        # total = sum(w for c, w in choices)
        total = sum(item['weight'] for item in choices)
        r = random.uniform(0, total)
        upto = 0
        for item in choices:
            if upto + item['weight'] >= r:
                return item['name']
            upto += item['weight']
        assert False, 'Shouldn\'t get here'

    def handle_lunchbot_command(self, command):
        """
        Takes a command from Slack chat directed at Lunchbot and performs the action
        if it is supported
        """
        if 'help' in command.lower():
            msg =   ('Here are the actions that Lunchbot can perform:\n'
                    'list restaurants                   -- lists all the restaurants Lunchbot supports and their weights\n'
                    'add restaurant <name> <weight>     -- add a new restaurant to the list of restaurants (if restaurant name has spaces please surround with quotations)\n'
                    'remove restaurant <name>           -- remove the restaurant from the list of restaurants\n')
        elif 'list restaurants' in command.lower():
            msg = ''
            for restaurant in self.RESTAURANTS:
                msg = '\n'.join([msg, '%s has weight %s' % (restaurant['name'], restaurant['weight'])])
        elif 'add restaurant' in command.lower():
            # Split command but keep quoted substrings as a single unit
            pieces = [p for p in re.split("( |\\\".*?\\\"|'.*?')", command) if p.strip()]
            # Get restaurant and weight to add from command
            restaurant = pieces[-2]
            weight = int(pieces[-1])
            # Remove quotations from restaurant string if there are any
            if restaurant[0] == '"':
                quotation = '"'
            else:
                quotation = '\''
            restaurant = restaurant.replace(quotation, '')

            # Check to see if restaurant is already in the list
            existing_restaurant = self.find_restaurant(restaurant)
            if existing_restaurant is not None:
                # Restaurant is in list, so update with new weight value
                msg = 'Updating restaurant %s with new weight %d (was %d)' % (restaurant, weight, existing_restaurant['weight'])
                restaurant_index = self.RESTAURANTS.index(restaurant)
                existing_restaurant['weight'] = weight
                self.RESTAURANTS[restaurant_index] = existing_restaurant
            else:
                # Restaurant is not in list so add as a new entry
                msg = 'Adding restaurant %s with weight %d' % (restaurant, weight)
                self.RESTAURANTS.append({
                    'name': restaurant,
                    'weight': weight
                })
            # Update data.json file and reload global variables
            self.update_data()
            self.read_data()
        elif 'remove restaurant' in command.lower():
            # Split command but keep quoted substrings as a single unit
            pieces = [p for p in re.split("( |\\\".*?\\\"|'.*?')", command) if p.strip()]
            # Get restaurant and weight to add from command
            restaurant = pieces[-1]
            # Remove quotations from restaurant string if there are any
            if restaurant[0] == '"':
                quotation = '"'
            else:
                quotation = '\''
            restaurant = restaurant.replace(quotation, '')

            # Check to see if restaurant is already in the list
            existing_restaurant = self.find_restaurant(restaurant)
            if existing_restaurant is not None:
                # Restaurant is in the list so remove it
                msg = 'Removing %s from the list of restaurants!' % restaurant
                self.RESTAURANTS.remove(existing_restaurant)
                self.update_data()
                self.read_data()
            else:
                msg = 'Uh oh! %s is not in the list of restaurants.' % restaurant
        else:
            msg = 'I\'m not smart enough to understand what you mean, sorry about that! Please type "Lunchbot help" to see what I do understand :)'

        self.SLACK_CLIENT.api_call('chat.postMessage', channel=self.CHANNEL, text=msg, as_user=True)

    def run(self):
        """
        Main loop/logic of lunchbot
        """
        if self.SLACK_CLIENT.rtm_connect():
            print 'Lunchbot connected and running!'
            while True:
                # Get current time and day
                now = datetime.now()
                current_time = now.strftime('%H:%M')
                day = now.strftime('%A')

                # Loop through messages and see if it's the correct time to print one
                for message in self.MESSAGES:
                    if current_time == message['time'] and day in message['days']:
                        msg = message['message']

                        # Append restaurant when eating out
                        if message['type'] == 'eating_out':
                            msg = '%s %s?' % (msg, self.weighted_choice(self.RESTAURANTS))

                        self.SLACK_CLIENT.api_call('chat.postMessage', channel=self.CHANNEL,
                                                   text=msg, as_user=True)

                # Get message from chat
                read_message = self.SLACK_CLIENT.rtm_read()
                if len(read_message) != 0:
                    message = read_message[0]
                    if 'text' in message and 'user' in message:
                        # Check if message was not sent by Lunchbot and is directed to lunchbot
                        if message['user'] != self.print_bot_id(self.BOT_NAME) and 'lunchbot' in message['text'].lower():
                            print 'Lunchbot is receiving a command!'
                            self.handle_lunchbot_command(read_message[0]['text'])
                
                time.sleep(self.READ_WEBSOCKET_DELAY)
        else:
            print 'Connection failed. Invalid Slack token or bot ID?'


if __name__ == "__main__":
    BOT = Lunchbot()
    BOT.print_bot_id(BOT.BOT_NAME)

    BOT.run()
