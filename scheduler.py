#!/usr/bin/python3

#########################################################  
# Calernder based scheduler to switch RF433 sockets     #
# using cli codesend                                    #
#                                                       #
# Extra options can be defined in the description       #
# filed of each event, using an ini-style format:       #
#   [random]                                            #
#   # add random offset for start/end time              #
#   # values can be positive or negative                #
#   # "all" option is applied to start and end          # 
#   start : max random time in minutes                  #
#   end : max random time in minutes                    #
#   all : max random time in minutes                    #
#                                                       #
#   [sun]                                               #
#   # replace the start/end time with the current       #
#   # sunrise or sunset time +/- offset                 #
#   start : rise or set                                 #
#   end : rise or set                                   #
#   start_offset : offset in minutes                    #
#   end_offset : offset in minutes                      #
#                                                       #
# Matthias Homann                                       #
# 2017-10-03                                            #
#########################################################

import configparser
import subprocess
from random import uniform
import sched, time
from datetime import datetime, date, timedelta
from sunrise_sunset import SunriseSunset
import caldav
from caldav.elements import dav, cdav
import RPi.GPIO as GPIO
import logging, sys

# set logging destination and level
# level: CRITICAL > ERROR > WARNING INFO > DEBUG > NOTSET
# filename='example.log' or stream=sys.stderr
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
#logging.debug('A debug message!')
#logging.info('We processed %d records', 10)


def print_time(a='Time'):
    print(a, time.strftime('%H:%M:%S'))

def rc_switch(switch,onoff,stime):
    if onoff:
      sendcode=switches[switch]['oncode']
    else:
      sendcode=switches[switch]['offcode']
#    print('RC:',stime, sendcode)
    s.enterabs(stime,1,subprocess.call,
        argument=([switches['DEFAULT']['rf433'],sendcode,
        switches[switch]['protocol'],switches[switch]['pulselength']],));

def gpio_switch(switch,onoff,stime):
# Set the pin to output (just to be sure...)
    try:
      GPIO.setup(int(switches[switch]['pin']), GPIO.OUT)
    except:
      print('GPIO setup error for pin',switches[switch]['pin'])
# Can directly use the Boolean variabe onoff since True=1=GPIO.HIGH
    s.enterabs(stime,1,GPIO.output,argument=(int(switches[switch]['pin']),onoff));
#    print ('GPIO:',stime,switches[switch]['pin'],onoff);

def gpio_pulse(switch,onoff,stime):
# Set the pin to output (just to be sure...)
    try:
      GPIO.setup(int(switches[switch]['pin']), GPIO.OUT)
    except:
      print('GPIO setup error for pin',switches[switch]['pin'])
# Get the duration of the pulse
    if onoff:
      pulsetime=float(switches[switch]['on'])
    else:
      pulsetime=float(switches[switch]['off'])
# Chek for maximum pulse length, e.g. 10s (configured in switches.ini)
    if pulsetime>float(switches['DEFAULT']['max_pulse']):
      print ('The pulse duration of',pulsetime,'s is too long, setting to max=',max_pulse);
      pulsetime=float(switches['DEFAULT']['max_pulse']);
    s.enterabs(stime,1,GPIO.output,argument=(int(switches[switch]['pin']),1));
    s.enterabs(stime+pulsetime,1,GPIO.output,argument=(int(switches[switch]['pin']),0));

def dummy_switch(switch,onoff,stime):
    s.enterabs(stime,1,print,argument=('Dummy: ',onoff));

# Switch command options
# usage: switch_type[type]()
switch_type = {
  'rc'    : rc_switch,
  'gpio'  : gpio_switch,
  'pulse' : gpio_pulse,
  'dummy' : dummy_switch,
  }
 
switches = 0

#############################################################
# MAIN                                                      #
#############################################################
def main():

  GPIO.setmode(GPIO.BCM)
  GPIO.setwarnings(False)

  # Timezone offset
  tzoffset = datetime.today().hour-datetime.utcnow().hour

  # Read ini file for RC switch definition
  # keys: oncode, offcode, protocol, pulselength
  # example: switches['switchname']['oncode']
  global switches
  switches = configparser.ConfigParser()
  switches.sections()
  switches.read('/etc/caltimer/switches.ini')
  # Caldav url
  try:
    url = switches['DEFAULT']['caldav']
  except:
    print('Missing or incorrect ini file, please check /etc/caltimer/switches.ini')
    return
  # Scheduler intervall in Minuten
  interval = int(switches['DEFAULT']['interval'])
  # Maximum pulse length for GPIO pulses
  # max_pulse = float(switches['DEFAULT']['max_pulse'])

  # event options
  event_options = configparser.ConfigParser()


  client = caldav.DAVClient(url)
  try:
    principal = client.principal()
  except:
    e = sys.exc_info()[0]
    print('Error to access the web calendar:', e )
    return
  calendars = principal.calendars()
  if len(calendars) == 0:
    print ('No calender found at URL:',url)
    return
  
  if len(calendars) > 0:
    calendar = next((c for c in calendars if c.name == switches['DEFAULT']['calname']), None)
#    if type(calendar) ==  type(None)  :
    if calendar is  None:
      print('Calendar',switches['DEFAULT']['calname'],'not found.')
      print('Available calendars:')
      for calendar in calendars:
        print(calendar.name)
      return
    print ("Using calendar", calendar)

    dt = datetime.today()
    dt = dt + timedelta(minutes = interval - dt.minute % interval, seconds = -(dt.second % 60), microseconds = -(dt.microsecond % 1000000))
    dt_end = dt+timedelta(minutes=interval)

    print ("Events between: ", dt,"and",dt_end,"\n")

    results = calendar.date_search(
        dt - timedelta(hours=tzoffset), dt_end - timedelta(hours=tzoffset) )

    r_time_1 = 0
    r_time_2 = 0
    
    #print (len(results))
    if len(results)>0:
        # calculate sunrise and sunset
        ro = SunriseSunset(datetime.now(), latitude=float(switches['DEFAULT']['latitude']),
            longitude=float(switches['DEFAULT']['longitude']), localOffset=float(switches['DEFAULT']['local_offset']))
        rise_time, set_time = ro.calculate()
        print ("Sunrise",rise_time,", Sunset", set_time,"\n")
        if False: # print event list
          for event in results:
            event.load()
            e = event.instance.vevent
            print ("Start: " + e.dtstart.value.strftime("%H:%M") + ", Ende: " + e.dtend.value.strftime("%H:%M"))
            print ("Betreff:"+ e.summary.value + ", Ort:" + e.location.value);
            print ("Beschreibung:\n"+ e.description.value + "\n")
            if not e.location.value in switches:
              print ("Undefinerter RC-Switch",e.location.value)
            
    # schedule events
        print_time("Define scheduler at")
        global s
        s = sched.scheduler(time.time, time.sleep)
        for event in results:
            event.load()
            e = event.instance.vevent
            e_start = e.dtstart.value.timestamp()
            e_end = e.dtend.value.timestamp()
            # check if start/stop events are in current time interval
            s_start = e_start >= dt.timestamp() and e_start < dt_end.timestamp()
            s_end = e_end >= dt.timestamp() and e_end < dt_end.timestamp()

            try:
              event_options.read_string(e.description.value)
            except:
              print('Description undefined or incorrect')
              event_options.read_string('[DEFAULT]') # read dummy settings to clear data from previous event
# print event options
#            for each_section in event_options.sections():
#              for (each_key, each_val) in event_options.items(each_section):
#                print (each_key,':',each_val)

            r_time_1 = 0
            r_time_2 = 0
            # if there are random numbers define
            if event_options.has_section('random'):
              if event_options.has_option('random','all'):
                try:
                  r_time_1 = uniform(0,float(event_options['random']['all'])*60) # calculate random value from defined range
                  r_time_2 = r_time_1
                except:
                  print ("Random all is incorrect! Format is 'all : 999'")
              if event_options.has_option('random','start'):
                try:
                  r_time_1 = uniform(0,float(event_options['random']['start'])*60) # calculate random value from defined range
                except:
                  print ("Random start is incorrect! Format is 'start : 999'")
              if event_options.has_option('random','end'):
                try:
                  r_time_2 = uniform(0,float(event_options['random']['end'])*60) # calculate random value from defined range
                except:
                  print ("Random end is incorrect! Format is 'end : 999'")
            if event_options.has_section('sun'):
              if event_options.has_option('sun','start'):
                if event_options['sun']['start'] == "rise":
                  e_start=rise_time.timestamp()
                elif event_options['sun']['start'] == "set":
                  e_start=set_time.timestamp()
                else:
                  print('Sunrise start time option is incorrect, valid options are "rise" or "set"')
                try: # add start offset
                  e_start=e_start+(float(event_options['sun']['start_offset'])*60) # sunrise + offset
                except:
                  print ("Sunrise start offset format is incorrect! Format is 'start_offset : 999'")
            if event_options.has_section('sun'):
              if event_options.has_option('sun','end'):
                if event_options['sun']['end'] == "rise":
                  e_end=rise_time.timestamp()
                elif event_options['sun']['end'] == "set":
                  e_end=set_time.timestamp()
                else:
                  print('Sunrise end time option is incorrect, valid options are "rise" or "set"')
                try: # add end offset
                  e_end=e_end+(float(event_options['sun']['end_offset'])*60) # sunset + offset  
                except:
                  print ("Sunset end offset format is incorrect! Format is 'end_offset : 999'")

            if s_start:
                print (e.location.value,"einschlaten um",datetime.fromtimestamp(e_start).strftime('%H:%M:%S'),"{0:+.1f} min".format(r_time_1/60))
#                try:
                switch_type[switches[e.location.value]['type']](e.location.value,True,e_start+r_time_1)
#                except:
#                  print('Error:',e.summary.value,'at',e_start,'+',r_time_1,'!')
            if s_end:
                print (e.location.value, "ausschalten",datetime.fromtimestamp(e_end).strftime('%H:%M:%S'),"{0:+.1f} min".format(r_time_2/60))
                try:
                  switch_type[switches[e.location.value]['type']](e.location.value,False,e_end+r_time_2)
                except:
                  print('Error:',e.summary.value,print_time(e_end))
#        print (s.queue)
        print_time("Start scheduler at")
        print()
        s.run()
    else:
        print ("No switching events in this time interval.")
  

if __name__ == "__main__":
    main()
