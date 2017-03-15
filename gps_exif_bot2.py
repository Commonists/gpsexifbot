#!/usr/bin/python

import sys, os
print os.environ['HOME']
sys.path.append(os.environ['HOME'] + '/core')

import pywikibot
import MySQLdb
import pyexiv2
import re
import math
import string
import unicodedata
import htmlentitydefs 
import marshal
import urllib
from urllib import FancyURLopener
from phpserialize import *
from datetime import timedelta
from datetime import datetime

# trap broken pyexiv
if 'ImageMetadata' not in dir(pyexiv2) :
  import socket
  print(socket.gethostname())
  sys.exit(1)

# look at images of the last two days
dt = timedelta(190)
cut = datetime.now() - dt

class MyOpener(FancyURLopener):
  version = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; it; rv:1.8.1.11) Gecko/20071127 Firefox/2.0.0.11'
        

myopener = MyOpener()
urllib.urlopen = MyOpener().open
urllib.urlretrieve = MyOpener().retrieve

   
def unescape_charref(ref) :
  name = ref[2:-1]
  base = 10
  if name.startswith("x") :
    name = name[1:]
    base = 16
  return unichr(int(name, base))
					  
def replace_entities(match) :
  ent = match.group()
  if ent[1] == "#":
    return unescape_charref(ent)
							      
  repl = htmlentitydefs.name2codepoint.get(ent[1:-1])
  if repl is not None :
    repl = unichr(repl)
  else :
    repl = ent
  return oepl
												    
def unescape(data) : 
  return re.sub(r"&#?[A-Za-z0-9]+?;", replace_entities, data) 


gpstrackusers = set( [ 'Ikiwaner' ] );

loc1RE = re.compile( '\{\{[Ll]ocation[ _]dec\|([^\|]+)\|([^\|\}]+)[\|\}]' )
loc2RE = re.compile( '\{\{[Ll]ocation[ _]dec\|([^\}\{]+)\}\}' )
loc3RE = re.compile( '\{\{[Ll]ocation\|([^\}\{]+)\}\}' )

nolocRE = re.compile( '\[\[[Cc]ategory:[Ll]ocation[ _]not[ _]applicable\]\]' )

gpsRE = re.compile( '\{\{(Template:|template:|10:|)[Gg]PS[_ ]EXIF\}\}(\n|)' )
#gpsRE = re.compile( '\{\{Template:[Gg]PS[ _]EXIF\}\}' )

latrefRE = re.compile( '^[NnSs]$' )
lonrefRE = re.compile( '^[EeOoWw]$' )

site = pywikibot.Site()


try:
  f = open( "badlist.gps", "rb" )
  badlist = marshal.load( f )
  #badlist = {}
  f.close()
except:
  badlist = {}

try:
  f = open( "taglist.gps", "rb" )
  taglist = marshal.load( f )
  f.close()
except:
  taglist = {}

try:
  connection = MySQLdb.connect(host="commonswiki.labsdb", db="commonswiki_p", read_default_file="~/replica.my.cnf" )
  cursor = connection.cursor() 
  cursor.execute( "create temporary table p50380g50970__temp.dump (tl_from int, score int)" )

  # select specific images (debug)
  #cursor.execute( "insert into p50380g50970__temp.dump SELECT page_id, 0 from image, page where page_namespace = 6 and img_name = page_title and img_name = 'Chur_de_la_basilique_Saint-Sauveur,_Dinan,_France.jpg'" )
  #cursor.execute( "insert into p50380g50970__temp.dump SELECT 25353345, 0" )
	
  # Go over all uploads of a specific user (manual)
  #cursor.execute( "insert into p50380g50970__temp.dump SELECT page_id, 0 from image, page where img_user_text = \"Niteshift\" and img_name = page_title and page_namespace = 6 and ( img_metadata like '%%\"GPSAltitude\"%%' or img_metadata like '%%\"GPSLatitudeRef\"%%' )" )

  print "Looking for GPS EXIF data (images > %s)"  % cut.strftime( "%Y%m%d%H%M%S" )
  cursor.execute( "insert /* SLOW_OK */ into p50380g50970__temp.dump SELECT page_id, 0 from image, page where img_timestamp > '%s' and CONVERT(img_name USING latin1) = page_title and page_namespace = 6 and ( img_metadata like '%%\"GPSAltitude\"%%' or img_metadata like '%%\"GPSLatitudeRef\"%%' )" % cut.strftime( "%Y%m%d%H%M%S" ) )
  print "Looking for {{Location}}";
  cursor.execute( "insert /* SLOW_OK */ into p50380g50970__temp.dump select tl_from, 1 from templatelinks where tl_namespace = 10 and tl_title = 'Location'" )
  print "Looking for {{Location dec}}";
  cursor.execute( "insert /* SLOW_OK */ into p50380g50970__temp.dump select tl_from, 1 from templatelinks where tl_namespace = 10 and tl_title = 'Location_dec'" )
  print "subtracting..."
  cursor.execute( "select /* SLOW_OK */ page_title, tl_from, SUM( score ) as s, img_metadata from p50380g50970__temp.dump, page, image where img_name = page_title and page_namespace = 6 and page_id = tl_from group by tl_from having s = 0" )
  print "fetching results..."

  data = cursor.fetchall() 
  fields = cursor.description
  cursor.close()

  # add to taglist if not previously visited
  for row in range(len(data)):
    name = data[row][0]
    #taglist[ name ] = True
    if not ( name in taglist ):
      taglist[ name ] = data[row][3]

  print "Looking for {{GPS EXIF}}";
  cursor = connection.cursor() 
  cursor.execute( "select /* SLOW_OK */ page_title, img_metadata from page, templatelinks, image where tl_namespace = 10 and tl_title = 'GPS_EXIF' and page_id = tl_from and page_namespace = 6 and page_title = img_name" )
  data = cursor.fetchall() 
  fields = cursor.description
  cursor.close()
  connection.close()

  # add to taglist regardless of previous visits
  for row in range(len(data)):
    name = data[row][0]
    taglist[ name ] = data[row][1]

  file = open( "taglist.gps", "wb" )
  marshal.dump( taglist, file )
  file.close()

except MySQLdb.OperationalError, message: 
  errorMessage = "Error %d:\n%s" % (message[ 0 ], message[ 1 ] ) 
  print errorMessage
  sys.exit(1)



#
# get potential images from taglist
#

#taglist = {}
#taglist['Calistoga,_California.jpeg'] = True

for name in taglist.keys() :
  if taglist[name] != False and not ( name in badlist ):

    print name
    try:
      exif = loads(taglist[name])
    except:
      print "Failed to unserialize EXIF data!"
      badlist[ name ] = True;
      continue


    page = pywikibot.Page(site, 'File:' + name.decode('utf-8') )
    text = ""

    if page.exists() :
      # follow redirects to the actual image page
      while True :
        try :
          text = page.get()
          break
        except pywikibot.IsRedirectPage :
          page = page.getRedirectTarget()
        except :
          print "Could not get page " + name
	  taglist[name] = False
          text = False
          break

    else :
      continue
	
    if text == False :
      continue

    # remove {{GPS EXIF}}
    oldtext = text
    text = gpsRE.sub( '', text )

    # Location not applicable
    if nolocRE.search( text ) != None :
      taglist[ name ] = False;
      print "Location not applicable"
      continue

    # already contains a Location
    if string.find(text, '{{Location' ) >= 0 :
	
      # already contains a generated Location
      if string.find(text, 'source:exif' ) >= 0 :
        print "HMM, %s looks already processed" % name;

        if oldtext != text :
          try:
            page.put(text, comment="removed gps exif request template")
          except:
            print "failed to save page"
            continue
          print "removed a superfluous gps exif request template"

        taglist[ name ] = False;
        continue
	
      # extract location to compare to exif
      lat_in_dec = 0
      lon_in_dec = 0

      #{{Location dec|47.5059|-122.0343|type:forest_region:US}}
      try :
        for match in loc1RE.findall(text) :
          lat_in_dec = float( match[0] )
          lon_in_dec = float( match[1] )
      except :
        lat_in_dec = 0
        lon_in_dec = 0


    # blocking template
    if string.find(text, '{{bots|deny=DschwenBot}}' ) >= 0 :
      print "Contains blocking template";
      taglist[ name ] = False
      continue

    # already contains a suggestion
    if string.find(text, '<!-- EXIF_BOT' ) >= 0 :
      print "HMM, looks already processed";

      if oldtext != text :
        try:
          page.put(text, comment="removed gps exif request template")
        except:
          print "failed to save page"
          continue
        print "removed a superfluous gps exif request template"

      taglist[ name ] = False
      continue

    # check if the metadata contains what we need (TODO)

    print "downloading http://commons.wikimedia.org/wiki/Special:Filepath/%s ..." % name
    try:
      urllib.urlretrieve( ( "http://commons.wikimedia.org/wiki/Special:Filepath/%s" % urllib.quote(name) ), ".temp.jpg" )
    except Exception, e:
      print "Exception while downloading:", e
      continue

    print "analyzing GPS EXIF data ...";

    try :
      metadata = pyexiv2.ImageMetadata( ".temp.jpg" )
      metadata.read()
	
      temp = '{{Location'

      lat_dec = 0.0;
      if 'Exif.GPSInfo.GPSLatitude' in metadata.exif_keys : 
        for i in range(0, 3):
          val = ( float(metadata['Exif.GPSInfo.GPSLatitude'].value[i].numerator) / 
                  float(metadata['Exif.GPSInfo.GPSLatitude'].value[i].denominator) )
          temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
          lat_dec = lat_dec * 60.0 + val

        ref = metadata['Exif.GPSInfo.GPSLatitudeRef'].value
      else :
        val = metadata['Xmp.exif.GPSLatitude'].value.degrees
        temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
        lat_dec = val
        val = metadata['Xmp.exif.GPSLatitude'].value.minutes
        temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
        lat_dec = lat_dec*60.0 + val
        val = metadata['Xmp.exif.GPSLatitude'].value.seconds
        if val != 0.0 :
          temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
          lat_dec = lat_dec*60.0 + val

        ref = metadata['Xmp.exif.GPSLatitude'].value.direction
      
      if ref == 'S' :	
        lat_dec = -lat_dec
      elif ref != 'N' :
        print "Broken lattitude ref!"
        temp = "<!-- GPS: Broken lattitude ref! --><br>" + temp
        ref = 'N'

      temp += '|' + ref
				
      lon_dec = 0.0;
      if 'Exif.GPSInfo.GPSLongitude' in metadata.exif_keys : 
        for i in range(0, 3):
          val = ( float(metadata['Exif.GPSInfo.GPSLongitude'].value[i].numerator) / 
                  float(metadata['Exif.GPSInfo.GPSLongitude'].value[i].denominator) )
          temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
          lon_dec = lon_dec * 60.0 + val

        ref = metadata['Exif.GPSInfo.GPSLongitudeRef'].value
      else :
        val = metadata['Xmp.exif.GPSLongitude'].value.degrees
        temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
        lon_dec = val
        val = metadata['Xmp.exif.GPSLongitude'].value.minutes
        temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
        lon_dec = lon_dec*60.0 + val
        val = metadata['Xmp.exif.GPSLongitude'].value.seconds
        if val != 0.0 :
          temp += ( "|%f" % ( val ) ).rstrip('0').rstrip('.')
          lon_dec = lon_dec*60.0 + val

        ref = metadata['Xmp.exif.GPSLongitude'].value.direction

      if ref == 'W' :
        lon_dec = -lon_dec
      elif ref != 'E' :
        print "Broken longitude ref!"
        temp = "<!-- GPS: Broken longitude ref! --><br>" + temp
        ref = 'E'
      
      temp +=  '|' + ref

    except Exception, e:
      print "Broken Tag", e
      taglist[ name ] = False;
      badlist[ name ] = True;

      # does the page contain {{GPS EXIF}} ?
      if oldtext != text :
        try:
          page.put(text, comment="image does not contain or contains broken GPS data; removed gps exif request template")
        except:
          print "failed to save page"
          continue
      
      continue

    #
    # Jump through several hoops to try to determine a heading and make [User:Ikiwaner] happy
    #

    heading = '?'
    try:
      val = ( float(metadata['Exif.GPSInfo.GPSImgDirection'].value.numerator) / 
              float(metadata['Exif.GPSInfo.GPSImgDirection'].value.denominator) )
      heading = ( "%f" % ( val ) ).rstrip('0').rstrip('.')
      print "Heading found :-)"

    except:
      print "No heading found :-("

      #try:
      #  val = ( float(metadata['Exif.GPSInfo.GPSTrack'].value.numerator) / 
      #          float(metadata['Exif.GPSInfo.GPSTrack'].value.denominator) )
      #  heading = ( "%f" % ( val ) ).rstrip('0').rstrip('.')
      #  print "Falling back on direction of movement instead :-/"
      #
      #except:
      #  print "No dir of movement found either :-("

    # a lot of cameras create dummy entries with a heading of 0, we do not trust those to be real
    if heading == 0 :
      heading = '?'

    #
    # deal with missing altitude data
    #
		
    try:
      if 'Exif.GPSInfo.GPSAltitude' in metadata.exif_keys :
        alt = ( float(metadata['Exif.GPSInfo.GPSAltitude'].value.numerator) / 
                float(metadata['Exif.GPSInfo.GPSAltitude'].value.denominator) )
      else :
        alt = ( float(metadata['Xmp.exif.GPSAltitude'].value.numerator) / 
                float(metadata['Xmp.exif.GPSAltitude'].value.denominator) )

      try:
        if int( metadata['Exif.GPSInfo.GPSAltitudeRef'].value ) == 1 :
          alt = -alt

      except:
        print "no AltitudeRef, assuming above sea level!"

      temp += ( "|alt:%f" % alt ).rstrip('0').rstrip('.') + "_" 
    except:
      print "No altitude data"
      temp += "|"

    temp += ( 'source:exif_heading:%s}}' % ( heading ) )
    print temp

    lat_dec /= 3600.0
    lon_dec /= 3600.0

    if lon_dec == 0.0 and lat_dec == 0.0 :
      print "apparently INVALID GPS data!"
      taglist[ name ] = False;
      badlist[ name ] = True;
      continue

    #
    # lat or long out of range
    #
    if lat_dec < -90 or lat_dec > 90 :
      print "Lat out of range", lat_dec
      taglist[ name ] = False;
      badlist[ name ] = True;
      continue

    #print "Old: %f,%f" % ( lat_in_dec, lon_in_dec )
    #print "New: %f,%f" % ( lat_dec, lon_dec )

    if string.find(text, '{{Location' ) < 0 :
      print "YAY! tagging..."

      m = re.search(r"\{\{[iI]nformation[\s\n]*\|", text, re.MULTILINE)
      if m is None :
        m = re.search(r"\{\{[aA]rtwork[\s\n]*\|", text, re.MULTILINE)

      if m is None :
        text2 = temp + "\n" + text
      else :
        last = ''
        infopos = m.start() + 2
        curl = 1
        squr = 0
        print infopos

        while infopos < len(text) :
          c = text[infopos]

          if c == '[' and last == '[' :
            squr += 1
            last = ''
          elif c == ']' and last == ']' :
            squr -= 1
            last = ''
          elif c == '{' and last == '{' :
            curl += 1
            last = ''
          elif c == '}' and last == '}' :
            curl -= 1
            last = ''
          else :
            last = c

          infopos += 1
          if curl == 0 and squr <= 0 :
            break

        text2 = text[:infopos] + "\n" + temp + text[infopos:]

      try:
        page.put(text2, comment="creating {{Location}} from EXIF data, please visit [[Commons:Geocoding]] for further information")
      except:
        print "failed to save page"
        continue
      taglist[ name ] = False;
    else :
      if string.find(text, '<!-- EXIF_BOT' ) < 0 and string.find(text, 'source:exif' ) < 0 :
	
        if math.fabs( lat_in_dec - lat_dec ) < 0.0001 and math.fabs( lon_in_dec - lon_dec ) < 0.0001 and (lat_in_dec !=0 or lon_in_dec !=0) :
          print "OK, existing geocoding seems reasonably accurate"
          taglist[ name ] = False;
          continue

        print "OK, just inserting hidden suggestion"
        temp = ( "%f|%f check EWNS!\n" % ( lat_dec, lon_dec ) ) + temp;
        text = '<!-- EXIF_BOT suggests: ' + temp + " -->\n" + text.replace( '{{GPS EXIF}}', '' )
        try:
          page.put(text, comment="adding suggested {{Location}} from EXIF data")
        except:
          print "failed to save page"
          continue
        taglist[ name ] = False;
      else :
        print "HMM, looks already processed";

        if oldtext != text :
          try:
            page.put(text, comment="removed gps exif request template")
          except:
            print "failed to save page"
            continue
          print "removed a superfluous gps exif request template"

        taglist[ name ] = False;
				

    file = open( "badlist.gps", "wb" )
    marshal.dump( badlist, file )
    file.close()

    file = open( "taglist.gps", "wb" )
    marshal.dump( taglist, file )
    file.close()


file = open( "badlist.gps", "wb" )
marshal.dump( badlist, file )
file.close()

file = open( "taglist.gps", "wb" )
marshal.dump( taglist, file )
file.close()

