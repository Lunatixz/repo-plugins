# -*- coding: utf-8 -*-
from __future__ import absolute_import,unicode_literals
import datetime
import json
import re
import xbmcaddon # pylint: disable=import-error
import xbmc # pylint: disable=import-error

from . import logging

try:
  # Python 2
  from urlparse import parse_qs
  from urlparse import urlparse
  from urlparse import urljoin
  from urllib import urlopen
  from urllib import unquote
except ImportError:
  # Python 3
  from urllib.parse import parse_qs
  from urllib.parse import urlparse
  from urllib.parse import urljoin
  from urllib.parse import unquote
  from urllib.request import urlopen

addon = xbmcaddon.Addon("plugin.video.svtplay")
THUMB_SIZE = "extralarge"

# Available bandwidths
BANDWIDTH = [300, 500, 900, 1600, 2500, 5000]

def getUrlParameters(arguments):
  """
  Return URL parameters as a dict from a query string
  """
  arguments = unquote(arguments)
  try:
    # Python 2 arguments is a byte string and needs to be decoded
    arguments = arguments.decode("utf-8")
  except AttributeError:
    # Python 3 str is already unicode and needs no decode
    pass
  logging.log("getUrlParameters: {}".format(arguments))
  if not arguments:
    return {}
  params = {}
  start = arguments.find("?") + 1
  pairs = arguments[start:].split("&")
  for pair in pairs:
    split = pair.split("=")
    if len(split) == 2:
      params[split[0]] = split[1]
  return params

def prepareImgUrl(url, baseUrl):
  if url.startswith("//"):
    url = url.lstrip("//")
    url = "http://" + url
  elif not (url.startswith("http://") or url.startswith("https://")) and baseUrl:
    url = baseUrl + url
  # Kodi has issues fetching images over SSL
  url = url.replace("https", "http")
  return url

def prepareThumb(thumbUrl, baseUrl):
  """
  Returns a thumbnail with size THUMB_SIZE
  """
  if not thumbUrl:
    return ""
  thumbUrl = prepareImgUrl(thumbUrl, baseUrl)
  thumbUrl = re.sub(r"\{format\}|small|medium|large|extralarge", THUMB_SIZE, thumbUrl)
  return thumbUrl

def getInputFromKeyboard(heading):
    keyboard = xbmc.Keyboard(heading=heading)
    keyboard.doModal()

    if keyboard.isConfirmed():
        text = keyboard.getText()

    return text

def prepareFanart(fanartUrl, baseUrl):
  """
  Returns a fanart image URL.
  """
  if not fanartUrl:
    return ""
  fanartUrl = prepareImgUrl(fanartUrl, baseUrl)
  fanartUrl = re.sub(r"\{format\}|small|medium|large|extralarge", "extralarge_imax", fanartUrl)
  return fanartUrl

def getStreamForBW(url):
  """
  Returns a stream URL for the set bandwidth,
  and an error message, if applicable.
  """
  low_bandwidth  = int(float(addon.getSetting("bandwidth")))
  high_bandwidth = getHighBw(low_bandwidth)
  f = urlopen(url)
  lines = f.readlines()
  hls_url = ""
  marker = "#EXT-X-STREAM-INF"
  found = False
  for line in lines:
    if found:
      # The stream url is on the line proceeding the header
      hls_url = line
      break
    if marker in line: # The header
      match = re.match(r'.*BANDWIDTH=(\d+)000.+', line)
      if match:
        if low_bandwidth < int(match.group(1)) < high_bandwidth:
          logging.log("Found stream with bandwidth " + match.group(1) + " for selected bandwidth " + str(low_bandwidth))
          found = True
  f.close()
  if found:
    hls_url = hls_url.rstrip()
    return_url = urljoin(url, hls_url)
    logging.log("Returned stream url: " + return_url)
    return (return_url, '')
  error_msg = "No stream found for bandwidth setting " + str(low_bandwidth)
  __errorMsg(error_msg)
  return (None, error_msg)

def getHighBw(low):
  """
  Returns the higher bandwidth boundary
  """
  i = BANDWIDTH.index(low)
  return BANDWIDTH[i+1]

def getVideoURL(json_obj):
  """
  Returns the video URL from a SVT JSON object.
  """
  video_url = None
  for video in json_obj["videoReferences"]:
    if video["format"] == "hls":
      alt = getAltUrl(video["url"])
      if alt is None:
        video_url = video["url"]
      else:
        video_url = alt
  return video_url

def getAltUrl(video_url):
  o = urlparse(video_url)
  query = parse_qs(o.query)
  try:
    alt = query["alt"][0]
    ufile = urlopen(alt)
    alt = ufile.geturl()
  except KeyError:
    alt = None
  return alt

def getSubtitleUrl(json_obj):
  """
  Returns a subtitleURL from a SVT JSON object.
  """
  url = None
  try:
    for subtitle in json_obj["subtitleReferences"]:
      if subtitle["url"].endswith(".wsrt"):
        url = subtitle["url"]
      else:
        if len(subtitle["url"]) > 0:
          logging.log("Skipping unknown subtitle: " + subtitle["url"])
  except KeyError:
    pass
  return url

def resolveShowJSON(json_obj):
  """
  Returns an object containing the video and subtitle URL for a show URL.
  Takes all settings into account.
  """
  video_url = None
  subtitle_url = None
  video_url = getVideoURL(json_obj)
  if video_url:
    subtitle_url = getSubtitleUrl(json_obj)
    extension = getVideoExtension(video_url)
    if extension == "HLS":
      if getSetting("bwselect"):
        (video_url, _) = getStreamForBW(video_url)
    video_url = cleanUrl(video_url)
  return {"videoUrl": video_url, "subtitleUrl": subtitle_url}

def cleanUrl(video_url):
  """
  Returns a cleaned version of the URL.

  Put all permanent and temporary cleaning rules here.
  """
  tmp = video_url.split("?")
  newparas = []
  if len(tmp) == 2:
    # query parameters exists
    newparas.append("?")
    paras = tmp[1].split("&")
    for para in paras:
      if para.startswith("cc1"):
        # Clean out subtitle parameters for iOS
        # causing playback issues in xbmc.
        pass
      elif para.startswith("alt"):
        # Web player specific parameter that
        # Kodi doesn't need.
        pass
      else:
        newparas.append(para)
  return tmp[0]+"&".join(newparas).replace("?&", "?")

def getVideoExtension(video_url):
  """
  Returns a string representation of the video extension.
  """
  # Remove all query strings
  url = video_url.split("?")[0]
  if url.endswith(".m3u8"):
    return "HLS"
  elif url.endswith(".mp4"):
    return "MP4"
  return None

def getSetting(setting):
  return True if addon.getSetting(setting) == "true" else False

def __errorMsg(msg):
  logging.error(msg)

def _infoMsg(msg):
  logging.log(msg)
