#!/usr/bin/env python
#-*- coding: utf-8 -*-

#
# Twittext - main.py
# - Hirotaka Kawata <info@techno-st.net>
# - http://www.techno-st.net/wiki/Twittext
#
#    Copyright (C) 2009 Hirotaka Kawata <info@techno-st.net>
#
#    This file is part of "Twittext".
#
#    Twittext is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Twittext is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Twittext.  If not, see <http://www.gnu.org/licenses/>.
#

import twoauth

from tools import *
from newinput import *

import curses
import locale
import datetime
import urllib2
import httplib

class twittext():
    def __init__(self, ckey, csecret, atoken, asecret):
        locale.setlocale(locale.LC_ALL, "")

        # twitter api instance
        self.api = twoauth.api(
            ckey, csecret, atoken, asecret)
        self.userlastget = datetime.datetime.now()

        # init temporary stack
        self.tmp = list()
        self.hist = list()

        self.statusfooter = ""
        self.autoreload = 60000 # ms        
    
    def run(self):
        while True:
            try:
                # start curses
                curses.wrapper(self.start)
                break
            except curses.error:
                pass

    def init(self):
        # curses init
        curses.use_default_colors()
        curses.curs_set(0)
        
        self.Y, self.X = self.stdcur.getmaxyx()

        # define color set
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)

        self.stdcur.idlok(1)
        self.stdcur.scrollok(True)
        self.stdcur.clear()

        # create subwin
        self.tlwin = self.stdcur.subwin(self.Y - 3, self.X, 2, 0)
        self.tlwin.idlok(1)
        self.tlwin.scrollok(True)
        self.tlwin.clear()
        
        self.headwin = self.stdcur.subwin(1, self.X, 1, 0)
        self.headwin.immedok(True)
        self.headwin.bkgd(" ", curses.color_pair(4))
        self.headwin.attrset(curses.color_pair(4))

        self.footwin = self.stdcur.subwin(self.Y - 1, 0)
        self.footwin.immedok(True)
        self.footwin.bkgd(" ", curses.color_pair(4))
        self.footwin.attrset(curses.color_pair(4))

        self.hometl = list()
        self.since_id = str()
        self.max_id = str()

        self.mode = 0
        self.stdcur.timeout(self.autoreload)

    def start(self, stdcur):
        # initialize
        self.stdcur = stdcur
        self.init()
        
        try:
            self.listed = listed_count(self.api)
        except:
            self.listed = -1

        while True:
            try:
                # show timeline
                while self.home():
                    y, x = self.stdcur.getmaxyx()
                    if (y, x) != (self.Y, self.X):
                        self.init()
                break
            except urllib2.HTTPError, e:
                # Twitter over capacity
                if e.code in (503, 502):
                    message = "Twitter Over Capacity..."
                elif e.code == 500:
                    message = "Twitter Server Error..."
                elif e.code == 400:
                    message = "Twitter REST API Rate Limited!"
                elif e.code == 404:
                    message = "Not Found..."
                elif e.code in (401, 403):
                    message = "Access Denied..."
                else:
                    raise

                self.mode = 0
                self.clear_head()
                self.stdcur.addstr(
                    0, 0,
                    "[Error] %s" % message,
                    curses.color_pair(1) | curses.A_BOLD)
                self.stdcur.refresh()
                self.stdcur.getch()
            except (httplib.BadStatusLine, urllib2.URLError):
                self.mode = 0
                self.clear_head()
                self.stdcur.addstr(
                    0, 0,
                    "[Error] HTTP Error",
                    curses.color_pair(1) | curses.A_BOLD)
                self.stdcur.refresh()
                self.stdcur.getch()
    
    def home(self):
        if self.mode >= 0: self.headwin.clear()
        self.footwin.clear()
        
        # Header
        header = "%d/%d (@%s) [Twittext]" % (
            self.api.ratelimit_remaining,
            self.api.ratelimit_limit,
            self.api.user["screen_name"])
        self.headwin.addstr(0, self.X - len(header) - 1, header)
        
        # Footer
        if (self.userlastget - datetime.datetime.now()).seconds > 300:
            me = self.api.user_show(self.api.user["screen_name"])
            self.api.user = me
            self.userlastget = datetime.datetime.now()
        else:
            me = self.api.user
        
        userinfo = """\
Total: %s tweets, \
Following: %s, Followers %s, \
Listed: %d""" % (
            me["statuses_count"], 
            me["friends_count"], me["followers_count"],
            self.listed)
        self.footwin.addstr(0, 0, userinfo)

        if self.mode != -1:
            # Backup for scroll
            self.oldmode = self.mode
            self.oldtmp = list(self.tmp)
        
        # timeline mode
        if self.mode == 0:
            self.loading("Home Timeline")
            self.hometl.extend(self.api.home_timeline(
                    count = self.Y, 
                    since_id = self.since_id, max_id = self.max_id))
            self.tl = self.hometl
            self.since_id = self.hometl[-1]["id"]
        elif self.mode == 1:
            self.loading("Tweets mentioning @%s" % 
                         (self.api.user["screen_name"]))
            self.tl = self.api.mentions(count = self.Y,
                                        max_id = self.max_id)
        elif self.mode == 2:
            tluser = self.tmp.pop()
            self.loading("@%s Timeline" % tluser)
            self.tl = self.api.user_timeline(tluser, count = self.Y,
                                             max_id = self.max_id)
        elif self.mode == 3:
            m = self.tmp.pop()
            if m == 1:
                self.loading("Retweets by others")
                self.tl = self.api.rt_to_me(count = self.Y,
                                            max_id = self.max_id)
            elif m == 2:
                self.loading("Retweets by you")
                self.tl = self.api.rt_by_me(count = self.Y,
                                            max_id = self.max_id)
            elif m == 3:
                self.loading("Your tweets, retweeted")
                self.tl = self.api.rt_of_me(count = self.Y,
                                            max_id = self.max_id)
        elif self.mode == 4:
            self.loading("Public Timeline")
            self.tl = self.api.public_timeline(count = self.Y,
                                               max_id = self.max_id)
        elif self.mode == 5:
            self.loading("Your Favorites")
            self.tl = self.api.favorites()
#        elif self.mode == 6:
#            q = self.tmp.pop()
#            self.loading("Real-time results for %s" % q)
#            self.tl = pass
        elif self.mode == 7:
            self.loading("Direct messages sent only to you")
            self.tl = self.api.dm_list()
        
        # print header
        self.stdcur.addstr(0, 0, "Post?: ")
        self.stdcur.addstr(" " * (self.X - 8), curses.A_UNDERLINE)
        
        self.mode = -1
        self.max_id = ""    
        
        # print timeline
        lshow = self.tl_show(self.tl)
        
        while True:
            # key input
            curses.flushinp()

            key = self.stdcur.getch(0, 7)
            
            if key == curses.KEY_DOWN:
                # Post Select Mode
                if lshow: self.tl_select(lshow)
            elif key in (curses.KEY_ENTER, 0x0a):
                # Update Status
                self.stdcur.move(0, 7)
                self.stdcur.clrtoeol()
                status = self.getstr()
                if status: self.post(status)
            elif key == ord("@"):
                # Show Reply
                self.mode = 1
            elif key == ord("u"):
                # User Timeline
                self.clear_head()
                self.stdcur.addstr(0, 0, "User?: @")
                self.stdcur.refresh()
                user = self.getstr()
                self.tmp.append(user)
                self.mode = 2
            elif key == ord("p"):
                # Public Timeline
                self.mode = 4
            elif key == ord("r"):
                # Retweet
                self.clear_head()
                self.stdcur.addstr(
                    0, 0, """\
1: Retweets by others, \
2: Retweets by you, \
3: Your tweets, retweeted""")
                n = self.stdcur.getch() - ord("0")
                if n in (1, 2, 3):
                    self.mode = 3
                    self.tmp.append(n)
            elif key == ord("f"):
                # Favorite
                self.mode = 5
            elif key == ord("F"):
                # Friendship
                self.clear_head()
                self.stdcur.addstr(0, 0, "User?: @")
                self.stdcur.refresh()
                user = self.getstr()
                self.friendship(user)
                self.stdcur.getch()
                continue
#            elif key == ord("s"):
#                # Search
#                self.stdcur.addstr(0, 0, "Search: ")
#                self.stdcur.clrtoeol()
#                q = self.getstr()
#                self.tmp.append(q)
#                self.mode = 6
            elif key == ord("d"):
                # Show Direct Messages
                self.mode = 7
            elif key == ord("D"):
                # Send Direct Message
                self.clear_head()
                self.stdcur.addstr("D User?: ")
                self.stdcur.refresh()
                user = self.getstr()
                if user:
                    self.dmessage(user)
            elif key in (-1, curses.KEY_LEFT, ord("h"), ord(" ")):
                # Home Timeline
                self.mode = 0
            elif key == ord("q"):
                # Quit
                return False
            else:
                continue

            break
        
        return True
    
    def clear_head(self):
        self.stdcur.move(0, 0)
        self.stdcur.clrtoeol()
        self.stdcur.refresh()
    
    def getstr(self, *args):
        self.stdcur.timeout(-1)
        s = mbgetstr(self.stdcur, *args)
        self.stdcur.timeout(self.autoreload)
        return s.encode("utf-8")
    
    def post(self, status, error = 0):
        self.clear_head()
        self.stdcur.addstr(0, 0, "Updating Status...")
        self.stdcur.refresh()
        
        post = "%s %s" % (
            status,
            self.statusfooter)

        try:
            self.api.status_update(post)
        except urllib2.HTTPError, e:
            # Twitter over capacity
            if error > 1:
                self.stdcur.addstr(" Error.",
                                   curses.color_pair(1) | curses.A_BOLD)
            elif e.code / 100 == 5:
                self.post(status, error + 1)
            else:
                raise
        else:
            self.stdcur.addstr(" OK.")

        self.stdcur.refresh()
    
    def reply(self, status):
        self.clear_head()
        self.stdcur.addstr(0, 0, "Reply: ")
        self.stdcur.refresh()

        name = status["user"]["screen_name"]
        reply_to = status["id"]

        replyhead = "@%s " % name
        self.stdcur.addstr(0, 7, replyhead)
        
        message = self.getstr()
        
        if message:
            self.clear_head()
            self.stdcur.addstr(0, 0, "Reply... ")
            self.stdcur.refresh()

            reply = ("%s%s" % (
                    replyhead, message.decode("utf-8"))).encode("utf-8")
            post = self.api.status_update(
                reply, in_reply_to_status_id = reply_to)
            
            self.stdcur.addstr("OK. (%s)" % post["id"])
            self.stdcur.refresh()
            self.stdcur.getch()

    def retweet(self, _id):
        self.clear_head()
        self.stdcur.addstr("Retweet? (Y/n)")
        self.stdcur.refresh()

        if self.stdcur.getch() != ord("n"):
            self.clear_head()
            self.stdcur.addstr(0, 0, "Retweet... ")
            self.stdcur.refresh()

            self.api.status_retweet(_id)
            self.stdcur.addstr("OK.")
            self.stdcur.refresh()
            self.stdcur.getch()
    
    def quotetweet(self, status):
        self.clear_head()
        self.stdcur.addstr("QT: ")
        message = self.getstr().decode("utf-8")
        
        if message:
            qt = "%s QT: @%s: %s" % (
                message, status["user"]["screen_name"], status["text"])
            self.post(qt.encode("utf-8"))
    
    def destroy(self, status):
        self.stdcur.move(0, 0)
        self.stdcur.clrtoeol()
        
        if int(self.api.user["id"]) == int(status["user"]["id"]):
            self.stdcur.addstr(0, 0, "Destroy? (Y/n): ")
            self.stdcur.refresh()
            
            if self.stdcur.getch() != ord("n"):
                self.stdcur.move(0, 0)
                self.stdcur.clrtoeol()
                self.stdcur.refresh()
                self.stdcur.addstr("Destroying: ")
                self.stdcur.refresh()
                self.api.status_destroy(status["id"])
                self.stdcur.addstr("OK.")
                self.stdcur.refresh()
                self.stdcur.getch()
            else:
                self.stdcur.move(0, 0)
                self.stdcur.clrtoeol()
        else:
            self.stdcur.addstr(0, 0, "[Error] Can't destroy this status...")
            self.stdcur.refresh()
            self.stdcur.getch()
    
    def friendship(self, user):
        self.stdcur.move(0, 0)
        self.stdcur.clrtoeol()
        
        fr = self.api.friends_show(user)
        ed = fr["source"]["followed_by"] == "true"
        ing = fr["source"]["following"] == "true"
        
        if ed:
            a = "<"
        else:
            a = " "
        
        if ing:
            b = ">"
        else:
            b = " "
        
        me = self.api.user["screen_name"]
        self.stdcur.addstr("@%s %s===%s @%s" % (me, a, b, user))
        self.stdcur.getch()

    def dmessage(self, user):
        self.clear_head()
        self.stdcur.addstr("D %s " % user)
        message = self.getstr()
        
        self.clear_head()
        self.stdcur.addstr("Sending Direct Message: ")
        self.stdcur.refresh()
        self.api.dm_new(user, message)
        self.stdcur.addstr("OK.")
        self.stdcur.refresh()
        self.stdcur.getch()

    def detail(self, status):
        self.clear_head()

        #self.headwin.addstr(0, 0, "[Status Detail]")
        #self.headwin.clrtoeol()

        self.footwin.addstr(0, 0, statusinfo(status))
        self.footwin.clrtoeol()

        self.tlwin.clear()
        self.tlwin.move(0, 0)
        s = """\
%s
(%s)
%s
%s

<%s>
""" % (
            status["user"]["screen_name"],
            status["user"]["name"],
#            status["user"]["following"],
#            "Protected" if status["user"]["protected"] == "true" else "",
            "-" * (self.X - 1),
            status["text"],
            status["id"],)
        self.tlwin.addstr(s.encode("utf-8"))
        self.tlwin.refresh()
        self.stdcur.getch()
       
    def tl_show(self, tl):
        self.tlwin.clear()
        
        # if Direct Messages?
        if "sender" in tl[0].keys():
            dm = True
            for m in tl:
                m["user"] = m["sender"]
        else:
            dm = False
        
        ret = list()
        i = 0
        for s in tl[::-1]:
            if not dm:
                # set curses attr (color)
                self.tlwin.attrset(attr_select(s, self.api.user))
            
            # print screen_name
            sname = "[%7s] " % (s["user"]["screen_name"][0:7])
            self.tlwin.addstr(i, 0, sname)
            
            # escape status text
            raw_str = s["text"]
            raw_str = replace_htmlentity(raw_str)
            raw_str = delete_notprintable(raw_str)
            
            (Y, X) = (self.Y - 3, self.X)
            
            # split status text
            sss = split_text(raw_str, X - len(sname))
            sss = sss[0:Y - i]
            
            for ss in sss:
                if i + 1 >= Y and cw_count(ss) + 10 >= X:
                    # last row fix
                    ss = ss[:-1]
                self.tlwin.addstr(i, 10, ss.encode("utf-8"))
                ret.append(s)
                i += 1
            
            if Y <= i:
                break
        
        # dispose...
        self.tlwin.attrset(0)
        self.tlwin.refresh()

        return ret

    def tl_select(self, lpost):
        self.tlwin.move(0, 0)
        self.tlwin.refresh()
        (Y, X) = (self.Y - 3, self.X)
        
        # if Direct Messages?
        if "sender" in lpost[0].keys():
            dm = True
            for m in lpost:
                m["user"] = m["sender"]
        else:
            dm = False

        i = 0
        
        while True:
            if not dm:
                attr = attr_select(lpost[i], self.api.user) & 0xffffff00 
            else:
                attr = curses.A_NORMAL

            s = self.tlwin.instr(i, 0)

            self.tlwin.move(i, 0)
            self.tlwin.clrtoeol()
            if i + 1 >= Y:
                # last row fix
                self.tlwin.addstr(s[:-1], attr | curses.A_STANDOUT)
            else:
                self.tlwin.addstr(s, attr | curses.A_STANDOUT)
                            
            #self.tlwin.move(i, 0)
            self.tlwin.refresh()

            # print screen_name
            u = lpost[i]["user"]
            p = "[Protected]" if u["protected"] == u"true" else ""
            h = "@%s (%s) %s" % (u["screen_name"], u["name"], p)
            self.stdcur.addstr(0, 0, h.encode("utf-8"))
            self.stdcur.clrtoeol()
            self.stdcur.refresh()
            
            # print created_at time
            self.footwin.addstr(0, 0, statusinfo(lpost[i]))
            self.footwin.clrtoeol()
            
            curses.flushinp()
            c = self.stdcur.getch(0, 0)

            if len(lpost) <= i:
                target = None
            else:
                target = lpost[i]

            # cursor point
            p = 0

            if c == curses.KEY_DOWN:
                # Down
                if i < Y - 1 and i < len(lpost) - 1:
                    p = 1
                else:
                    # scroll
                    self.mode = self.oldmode
                    self.tmp = list(self.oldtmp)
                    self.max_id = target["id"]
                    self.since_id = ""
                    self.hist.append(lpost[0]["id"])
                    break
            elif c == curses.KEY_UP:
                # Up
                if i > 0:
                    p = -1
                else:
                    # scroll
                    if self.hist:
                        self.mode = self.oldmode
                        self.tmp = list(self.oldtmp)
                        self.max_id = self.hist.pop()
                        self.since_id = ""
                        break
            elif c in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 0x1b):
                # Return
                break
            elif target:
                if c in (curses.KEY_ENTER, 0x0a, ord("@")):
                    # Reply
                    self.reply(target)
                elif c == ord("r"):
                    # Retweet
                    self.retweet(target["id"])
                elif c == ord("q"):
                    # Quote tweet
                    self.quotetweet(target)
                elif c in (curses.KEY_RIGHT, ord("u")):
                    # Show User Timeline
                    self.mode = 2
                    self.tmp.append(target["user"]["screen_name"])
                    break
                elif c == ord("U"):
                    # Show reply_to User Timeline
                    user = split_user(target["text"])
                    if user:
                        self.mode = 2
                        self.tmp.append(user)
                        break
                    else:
                        continue
                elif c == ord("d"):
                    # Destroy
                    self.destroy(target)
                elif c == ord("D"):
                    # Direct Message
                    self.dmessage(target["user"]["screen_name"])
                elif c == ord("f"):
                    # Favorite
                    self.stdcur.addstr(0, 0, "Favorite: ")
                    self.stdcur.clrtoeol()
                    self.api.favorite_create(target["id"])
                    self.stdcur.addstr("OK. (%s)" % target["id"])
                    self.stdcur.getch()
                elif c == ord("F"):
                    # Friendship
                    self.friendship(target["user"]["screen_name"])
                elif c == ord("t"):
                    # Show reply_to
                    if target["in_reply_to_status_id"]:
                        self.detail(
                            self.api.status_show(
                                target["in_reply_to_status_id"]))
                        break
                    else:
                        continue
                else:
                    continue
            else:
                continue
            
            self.tlwin.move(i, 0)
            self.tlwin.clrtoeol()

            if i + 1 >= Y:
                # last row fix
                self.tlwin.addstr(s[:-1], attr)
            else:
                self.tlwin.addstr(s, attr)

            i += p
            
            #self.tlwin.move(i, 0)
            self.tlwin.refresh()
        
        return

    def loading(self, name):
        self.tlname = name
        self.headwin.addstr(0, 0, "[%s]" % name)

        self.tlwin.clear()
        self.tlwin.refresh()
        
        self.clear_head()
        self.stdcur.addstr(0, 0, "Loading...")
        self.stdcur.refresh()