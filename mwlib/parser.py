#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2007-2008 PediaPress GmbH
# See README.txt for additional licensing information.

import sys
import os
import re

from mwlib.scanner import tokenize, TagToken, EndTagToken
from mwlib.log import Log

log = Log("parser")


tag_li = TagToken("li")
tag_div = TagToken("div")

class TokenSet(object):
    def __init__(self, lst):
        self.types = set()
        self.values = set()
        
        for x in lst:
            if isinstance(x, type):
                self.types.add(x)
            else:
                self.values.add(x)

    def __contains__(self, x):
        return x in self.values or type(x) in self.types
        
FirstAtom = TokenSet(['TEXT', 'URL', 'SPECIAL', '[[', 'MATH', '\n',
                      'BEGINTABLE', 'STYLE', 'TIMELINE', 'ITEM', 'URLLINK',
                      TagToken])

FirstParagraph = TokenSet(['SPECIAL', 'URL', 'TEXT', 'TIMELINE', '[[', 'STYLE', 'BEGINTABLE', 'ITEM',
                           'PRE', 'MATH', '\n', 'PRE', 'EOLSTYLE', 'URLLINK',
                           TagToken])

    
def show(out, node, indent=0):
    print >>out, "    "*indent, node
    for x in node:
        show(out, x, indent+1)


paramrx = re.compile("(?P<name>\w+) *= *(?P<value>(?:(?:\".*?\")|(?:(?:\w|[%:])+)))")
def parseParams(s):
    def style2dict(s):
        res = {}
        for x in s.split(';'):
            if ':' in x:
                var, value = x.split(':', 1)
                var=var.strip()
                value = value.strip()
                res[var] = value

        return res
    
    def maybeInt(v):
        try:
            return int(v)
        except:
            return v
    
    r = {}
    for name, value in paramrx.findall(s):
        if value.startswith('"'):
            value = value[1:-1]
            
        if name=='style':
            value = style2dict(value)
            r['style'] = value
        else:
            r[name] = maybeInt(value)
    return r


    

class Node(object):
    caption = ''

    def __init__(self, caption=''):
        self.children = []
        self.caption = caption

    def hasContent(self):
        for x in self.children:
            if x.hasContent():
                return True
        return False
    
    def append(self, c, merge=False):
        if c is None:
            return

        if merge and type(c)==Text and self.children and type(self.children[-1])==Text:
            self.children[-1].caption += c.caption
        else:            
            self.children.append(c)

    def __iter__(self):
        for x in self.children:
            yield x

    def __repr__(self):
        return "%s %r: %s children" % (self.__class__.__name__, self.caption, len(self.children))

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
                and self.caption == other.caption
                and self.children == other.children)

    def __ne__(self, other):
        return not(self==other)

    def allchildren(self): # name is broken, returns self, which is not a child
        yield self 
        for c in self.children:
            for x in c.allchildren():
                yield x        

    def find(self, tp):
        """find instances of type tp in self.allchildren()"""
        return [x for x in self.allchildren() if isinstance(x, tp)]


    def filter(self, fun):
        for x in self.allchildren():
            if fun(x):
                yield x

    def _asText(self, out):
        out.write(self.caption)
        for x in self.children:
            x._asText(out)
        
    def asText(self, ):
        from StringIO import StringIO
        out = StringIO()
        self._asText(out)
        return out.getvalue()
                    
class Math(Node): pass
class Ref(Node): pass
class Item(Node): pass
class ItemList(Node):
    numbered = False
    def append(self, node, merge=False):
        if not isinstance(node, Item):
            c=Item()
            c.append(node)
            self.children.append(c)
        else:
            self.children.append(node)

class Style(Node): pass
class Book(Node): pass
class Magic(Node): pass
class Chapter(Node): pass
class Article(Node): pass
class Paragraph(Node): pass
class Section(Node): pass
class Timeline(Node): pass
class TagNode(Node): pass
class PreFormatted(TagNode): pass
class URL(Node): pass
class NamedURL(Node): pass



class _VListNode(Node):
    def __init__(self, caption=''):
        Node.__init__(self, caption)
        self.vlist = {}

    def __repr__(self):
        return "%s %r %s: %s children" % (self.__class__.__name__, self.caption, self.vlist, len(self.children))
    
class Table(_VListNode):
    pass

class Row(_VListNode):
    pass

class Cell(_VListNode):
    pass

class Caption(_VListNode):
    pass

class Link(Node):
    target = None
    
    specialPrefixes = set([
        # English
        "wikipedia", "wiktionary", "wikibooks", "wikisource", "wikiquote", "meta", "talk",
        "commons", "wikinews", "template", "wikitravel", "help",
        # German
        "vorlage",
        # Spanish
    ])
    
    imageKeywords = set([
        "image", "imagen", "bild", "archivo", "rikcha", "plik", "fichier", "file",
        u"ta'ãnga"
    ])
    
    categoryKeywords = set([
        "category", "kategorie", "categor\\xeda", u"\\xf1emohenda"
    ])
    
    from mwlib.lang import languages
    colon = False

    def hasContent(self):
        if self.target:
            return True
        return False
        
    def _specialize(self):
        if not self.children:
            return

        if type(self.children[0]) != Text:
            return
            
        self.target = target = self.children[0].caption.strip()
        del self.children[0]
        if self.children and self.children[0] == Control("|"):
            del self.children[0]
        
        pic = self.target
        if pic.startswith(':'):
            self.colon = True
            
        
        
        # pic == "Bild:Wappen_von_Budenheim.png"
        
        pic = pic.strip(': ')
        if ':' not in pic:
            return
            
        linktype, pic = pic.split(':', 1)
        linktype = linktype.lower().strip(" :")
        
        if linktype in self.categoryKeywords:
            self.__class__ = CategoryLink
            self.target = pic.strip()
            return

        if linktype in self.specialPrefixes:
            self.__class__ = SpecialLink
            self.target = pic.strip()
            self.ns = linktype            

            return

        if linktype in self.languages:
            self.__class__ = LangLink
            return
            
        
        if linktype not in self.imageKeywords:
            # assume a LangLink
            log.info("Unknown linktype:", repr(linktype))
            if len(linktype) in [2, 3]:
                self.__class__ = LangLink
            return
        
        
        # pic == "Wappen_von_Budenheim.png"
        
        # WTB: See es.wikipedia.org/wiki/Provincia_de_Lima
        #try:
        #    prefix, suffix = pic.rsplit('.', 1)
        #except ValueError:
        #    return
        #if suffix.lower() in ['jpg', 'jpeg', 'gif', 'png', 'svg']:

        self.__class__ = ImageLink
        self.target = pic.strip()



        idx = 0
        last = []
        
        while idx<len(self.children):
            x = self.children[idx]
            if x == Control("|"):
                if idx:
                    last = self.children[:idx]
                    
                del self.children[:idx+1]
                idx = 0
                continue

            if not type(x)==Text:
                idx += 1
                continue

            x = x.caption.lower()
            
            if x == 'thumb' or x=='thumbnail':
                self.thumb = True
                del self.children[idx]
                continue

            if x in ['left', 'right', 'center', 'none']:
                self.align = x
                del self.children[idx]
                continue

            if x == 'frame' or x=='framed' or x=='enframed':
                self.frame = True
                del self.children[idx]
                continue
            

            if x.endswith('px'):
                # x200px
                # 100x200px
                # 200px
                x = x[:-2]
                width, height = (x.split('x')+['0'])[:2]
                try:
                    width = int(width)
                except ValueError:
                    width = 0

                try:
                    height = int(height)
                except ValueError:
                    height = 0

                self.width = width
                self.height = height
                del self.children[idx]
                continue
            
            idx += 1
        
        if not self.children:
            self.children = last
            
class ImageLink(Link):
    target = None
    width = None
    height = None
    align = ''
    thumb = False
    frame = False
    
    def isInline(self):
        return not bool(self.align or self.thumb or self.frame)
    
class LangLink(Link):
    pass

class CategoryLink(Link):
    pass

class SpecialLink(Link):
    pass

            
class Text(Node):
    def __repr__(self):
        return repr(self.caption)
    
    def __init__(self, txt):
        self.caption = txt
        self.children = []

    def hasContent(self):
        if self.caption.strip():
            return True
        return False
    
class Control(Text):
    pass

def _parseAtomFromString(s):
    from mwlib import scanner
    tokens = scanner.tokenize(s)
    p=Parser(tokens)
    try:
        return p.parseAtom()
    except Exception, err:
        log.error("exception while parsing %r: %r" % (s, err))
        return None

                  
    
def parse_fields_in_imagemap(imap):
    
    if imap.image:
        imap.imagelink = _parseAtomFromString(u'[['+imap.image+']]')
        if not isinstance(imap.imagelink, ImageLink):
            imap.imagelink = None

    # FIXME: the links of objects inside 'entries' array should also be parsed
    
    
def append_br_tag(node):
    """append a self-closing 'br' TagNode"""
    br = TagNode("br")
    br.starttext = '<br />'
    br.endtext = ''
    node.append(br)
            
class Parser(object):
    def __init__(self, tokens, name=''):
        self.tokens = tokens
        self.pos = 0
        self.name = name
        self.lastpos = 0
        self.count = 0

    @property
    def token(self):
        t=self.tokens[self.pos]
        if self.pos == self.lastpos:
            self.count += 1
            if self.count > 500:
                from mwlib.caller import caller

                raise RuntimeError("internal parser error: %s" % ((self.pos, t, caller()), ))
        else:
            self.count = 0
            self.lastpos = self.pos


        return t
    
    

    @property
    def left(self):
        return self.pos < len(self.tokens)

    def next(self):
        self.pos += 1

    def parseAtom(self):
        token = self.token
        
        if token[0]=='TEXT':
            self.next()
            return Text(token[1])
        elif token[0]=='URL':
            self.next()            
            return URL(token[1])
        elif token[0]=='URLLINK':
            return self.parseUrlLink()        
        elif token[0]=='SPECIAL':
            self.next()
            return Text(token[1])
        elif token[0]=='[[':
            return self.parseLink()
        elif token[0]=='MATH':
            return self.parseMath()
        elif token[0]=='\n':
            self.next()            
            return Text(token[1])
        elif token[0]=='BEGINTABLE':
            return self.parseTable()
        elif token[0]=='STYLE':
            return self.parseStyle()
        elif token[0]=='TIMELINE':
            return self.parseTimeline()
        elif token[0]=='ITEM':
            return self.parseItemList()
        elif isinstance(token[0], TagToken):
            return self.parseTagToken()
        else:
            raise RuntimeError("not handled: %s" % (token,))

    def parseUrlLink(self):
        u = self.token[1][1:]
        n = Node()
        n.append(Text("["))
        n.append(URL(u))
        
        self.next()
            
        while self.left:
            if self.tokens[self.pos:self.pos+2] == [(']]', ']]'), ('SPECIAL', u']')]:                
                self.tokens[self.pos:self.pos+2] = [('SPECIAL', ']'), (']]', ']]')]
                
            token = self.token

                
            if token[0] == 'SPECIAL' and token[1]==']':
                self.next()
                n.__class__ = NamedURL
                n.caption = u
                del n.children[:2]
                break
            elif token[0] in FirstAtom:
                n.append(self.parseAtom())
            else:
                break
                
        return n
            
        
    def parseArticle(self):
        a=Article(self.name)
            
        while self.left:
            token = self.token
            if token[0] == 'SECTION':
                a.append(self.parseSection())
            elif token[0]=='BREAK':
                self.next()
            elif token[0] in FirstParagraph:
                a.append(self.parseParagraph())
            else:
                log.info("in parseArticle: skipping", token)
                self.next()
                
        return a
            
    def parseLink(self):
        break_at = TokenSet(['BREAK', EndTagToken, 'SECTION'])
                             
        obj = Link()
        self.next()
        while self.left:
            token = self.token
            if token[0] == ']]':
                self.next()
                break
            elif token[0]=='SPECIAL' and token[1]==']':
                self.next()
                break
            elif token[1] == '|' or token[1]=="||":
                obj.append(Control('|'))
                self.next()
            elif token[0]=='TEXT' or token[0]=='SPECIAL' or token[0]=='\n':
                obj.append(Text(token[1]), merge=True)
                self.next()
            elif token[0] in break_at:
                break
            elif token[0] in FirstAtom:
                obj.append(self.parseAtom())
            elif token[1].startswith("|"):
                obj.append(Control("|"))
                obj.append(Text(token[1][1:]))
                self.next()
            else:
                log.info("assuming text in parseLink", token)
                obj.append(Text(token[1]), merge=True)
                self.next()

        obj._specialize()
            
        return obj
    
    def parseTag(self):
        token = self.token[0]
        
        n = TagNode(token.t)
        if token.values:
            n.values = token.values
        n.vlist = parseParams(self.token[1])

        n.starttext = token.text
        n.endtext = u'</%s>' % token.t
        self.next()

        if token.selfClosing:
            return n
        
        
        end = EndTagToken(token.t)
        
        while self.left:
            token = self.token
            if token[0]==end:
                n.endtext = token[0].text
                self.next()
                break
            elif token[0]=='BREAK':
                self.next()
            else:
                if token[0] not in FirstParagraph:
                    log.warn("tag not closed", n, token)
                    break
                n.append(self.parseParagraph())
                
        return n

    def parsePRETag(self):
        token = self.token[0]
        if token.t.lower()=='pre':
            n=PreFormatted()
        else:
            n=TagNode(token.t)
            n.starttext = ''
            n.endtext = ''

        n.vlist = parseParams(self.token[1])
        
        end = EndTagToken(self.token[0].t)
        self.next()
        
        txt = []
        while self.left:
            token = self.token
            if token[0]==end:
                self.next()
                break
            txt.append(token[1])
            self.next()

        n.append(Text("".join(txt)))
        return n

    parseCODETag = parsePRETag
    parseSOURCETag = parsePRETag
    def parseA7831D532A30DF0CD772BBC895944EC1Tag(self):
        p = self.parseTag()
        p.__class__ = Magic
        return p    

    parseREFTag = parseTag
    parseREFERENCESTag = parseTag
    
    parseDIVTag = parseTag
    parseSPANTag = parseTag
    parseSUPTag = parseTag
    parseINDEXTag = parseTag
    parseTTTag = parseTag

    parseH1Tag = parseTag
    parseH2Tag = parseTag
    parseH3Tag = parseTag
    parseH4Tag = parseTag
    parseH5Tag = parseTag
    parseH6Tag = parseTag
    
    parseINPUTBOXTag = parseTag

    parseRSSTag = parseTag

    parseSTRIKETag = parseTag
    parseCODETag = parseTag
    parseDELTag = parseTag
    parseINSTag = parseTag
    parseCENTERTag = parseTag
    parseSTARTFEEDTag = parseTag
    parseENDFEEDTag = parseTag
    parseCENTERTag = parseTag

    def parseGALLERYTag(self):
        node = self.parseTag()
        txt = "".join(x.caption for x in node.find(Text))
        #print "GALLERY:", repr(txt)

        children=[]

        lines = [x.strip() for x in txt.split("\n")]
        for x in lines:
            if not x:
                continue

            # either image link or text inside
            # FIXME: Styles and links in text are ignored!
            n=_parseAtomFromString(u'[['+x+']]')

            if isinstance(n, ImageLink):
                children.append(n)
            else:
                children.append(Text(x))

        node.children=children

        return node
    
    def parseIMAGEMAPTag(self):
        node = self.parseTag()
        txt = "".join(x.caption for x in node.find(Text))
        #from mwlib import imgmap
        #node.imagemap = imgmap.ImageMapFromString(txt)

        class FakeImageMap(object):
            pass

        node.imagemap = FakeImageMap()
        node.imagemap.entries = []
        node.imagemap.imagelink = None
        match = re.search('Image:.*', txt)

        if match:
            node.imagemap.image = match.group(0)
        else:
            node.imagemap.image = None

        parse_fields_in_imagemap(node.imagemap)

        #print node.imagemap
        return node

    def parseSection(self):
        s = Section()
        
        level = self.token[1].count('=')
        s.level = level
        closelevel = 0

        self.next()

        title = Node()
        while self.left:
            token = self.token
            
            if token[0] == 'ENDSECTION':
                closelevel = self.token[1].count('=')
                self.next()
                break
            elif token[0] == '[[':
                title.append(self.parseLink())
            elif token[0] == "STYLE":
                title.append(self.parseStyle())
            elif token[0] == 'TEXT':
                self.next()
                title.append(Text(token[1]))
            elif isinstance(token[0], TagToken):
                title.append(self.parseTagToken())
            elif token[0] == 'URLLINK':
                title.append(self.parseUrlLink())
            elif token[0] == 'MATH':
                title.append(self.parseMath())
            else:
                self.next()
                title.append(Text(token[1]))

        s.level = min(level, closelevel)
        if s.level==0:
            title.children.insert(0, Text("="*level))
            s.__class__ = Node
        else:
            diff = closelevel-level
            if diff>0:
                title.append(Text("="*diff))
            elif diff<0:
                title.children.insert(0, Text("="*(-diff)))
            
        s.append(title)


        while self.left:
            token = self.token
            if token[0] == 'SECTION':
                if token[1].count('=') <= level:
                    return s
                
                s.append(self.parseSection())
            elif token[0] in FirstParagraph:
                s.append(self.parseParagraph())
            else:
                log.info("in parseSection: skipping", token)
                break
                
        return s

    def parseStyle(self):
        end = self.token[1]
        b = Style(self.token[1])
        self.next()

        break_at = TokenSet(['BREAK', '\n', 'ENDEOLSTYLE', 'SECTION', 'ENDSECTION',
                             'BEGINTABLE', ']]', 'ROW', 'COLUMN', 'ENDTABLE', EndTagToken])
        
        while self.left:
            token = self.token
            if token[0]=="STYLE":
                if token[1]==end:
                    self.next()
                    break
                else:
                    new = token[1]
                    if end=="'''''":
                        if token[1]=="''":
                            new = "'''"
                        else:
                            new = "''"
                    elif end=="''":
                        if token[1]=="'''":
                            new = "'''''"
                        elif token[1]=="'''''":
                            new = "'''"
                    elif end=="'''":
                        if token[1]=="''":
                            new = "'''''"
                        elif token[1]=="'''''":
                            new = "''"
                        
                    self.tokens[self.pos] = ("STYLE", new)
                    break
            elif token[0] in break_at:
                break
            elif token[0] in FirstAtom:
                b.append(self.parseAtom())
            else:
                log.info("assuming text in parseStyle", token)
                b.append(Text(token[1]))
                self.next()

        return b
    

    def parseColumn(self):
        token = self.token
        c = Cell()

        params = ''
        if "|" in token[1] or "!" in token[1]: # not a html cell
            # search for the first occurence of "||", "|", "\n" in the next tokens
            # if it's a "|" we have a parameter list
            self.next()
            savepos = self.pos

            while self.left:
                token = self.token
                self.next()
                if token[0] in ("\n", "BREAK", "[[", "ROW", "ENDTABLE"):
                    params = ''
                    self.pos = savepos
                    break
                elif (token[0]=='SPECIAL' or token[0]=='COLUMN') and token[1]=='|':
                    break
                params += token[1]

            c.vlist = parseParams(params)

        elif token[0]=='COLUMN':   # html cell
            params=parseParams(token[1])
            #print "CELLTOKEN:", token
            #print "PARAMS:", params
            c.vlist = params
            self.next()



        while self.left:
            token = self.token
            if token[0] in ("COLUMN", "ENDTABLE", "ROW"):
                break
            
            if token[0] == 'BEGINTABLE':
                c.append(self.parseTable())
            elif token[0]=='SPECIAL' and token[1] == '|':
                self.next()
            elif token[0] == 'SECTION':
                c.append(self.parseSection())
            elif token[0] in FirstParagraph:
                c.append(self.parseParagraph())
            elif isinstance(token[0], EndTagToken):
                log.info("ignoring %r in parseColumn" % (token,))
                self.next()
            else:
                log.info("assuming text in parseColumn", token)
                c.append(Text(token[1]))
                self.next()

        return c
    
                
    def parseRow(self):
        r = Row()
        r.vlist={}

        token = self.token
        params = ''
        if token[0]=='ROW':
            self.next()
            if "|-" in token[1]:
                # everything till the next newline/break is a parameter list
                while self.left:
                    token = self.token
                    if token[0]=='\n' or token[0]=='BREAK':
                        break
                    else:
                        params += token[1]
                    self.next()
                r.vlist = parseParams(params)

            else:
                # html row
                r.vlist = parseParams(token[1])

            
        while self.left:
            token = self.token
            if token[0] == 'COLUMN':
                r.append(self.parseColumn())
            elif token[0] == 'ENDTABLE':
                return r
            elif token[0] == 'ROW':
                return r
            elif token[0] == 'BREAK':
                self.next()
            elif token[0]=='\n':
                self.next()
            else:
                log.warn("skipping in parseRow: %r" % (token,))
                self.next()
        return r
    
    def parseCaption(self):
        token = self.token
        self.next()
        n = Caption()
        params = ""
        if token[1].strip().startswith("|+"):
            # search for the first occurence of "||", "|", "\n" in the next tokens
            # if it's a "|" we have a parameter list
            savepos = self.pos
            while self.left:
                token = self.token
                self.next()
                if token[0] in ("\n", "BREAK", "[[", "ROW", "COLUMN", "ENDTABLE"):
                    params = ''
                    self.pos = savepos
                    break
                elif token[0]=='SPECIAL' and token[1]=='|':
                    break
                params += token[1]

        n.vlist = parseParams(params)
        
        while self.left:
            token = self.token
            if token[0] in ('TEXT' , 'SPECIAL', '\n'):
                if token[1]!='|':
                    n.append(Text(token[1]))
                self.next()
            elif token[0] == 'STYLE':
                n.append(self.parseStyle())
            elif isinstance(token[0], TagToken):
                n.append(self.parseTagToken())
            elif token[0] == '[[':
                n.append(self.parseLink())
            else:
                break
        return n
            
    def parseTable(self):
        token = self.token
        self.next()
        t = Table()

        params = ""
        if "{|" in token[1]:   # not a <table> tag
            # everything till the next newline/break is a parameter list
            while self.left:
                token = self.token
                if token[0]=='\n' or token[0]=='BREAK':
                    break
                else:
                    params += token[1]
                self.next()
            t.vlist = parseParams(params)
        else:
            t.vlist = parseParams(token[1])

        while self.left:
            token = self.token
            if token[0]=='ROW' or token[0]=='COLUMN':
                t.append(self.parseRow())
            elif token[0]=='TABLECAPTION':
                t.append(self.parseCaption())
            elif token[0]=='ENDTABLE':
                self.next()
                break
            elif token[0]=='\n':
                self.next()
            else:
                log.warn("skipping in parseTable", token)
                self.next()
                #t.append(self.parseRow())

        return t

    def parseMath(self):
        self.next()
        caption = u''
        while self.left:
            token = self.token
            self.next()            
            if token[0]=='ENDMATH':
                break
            caption += token[1]
        return Math(caption)                
                
    def parseTimeline(self):
        t=Timeline()
        self.next()
        snippets = []
        while self.left:
            token = self.token
            self.next()
            if token[0]=='TIMELINE':
                break
            snippets.append(token[1])
        t.caption = "".join(snippets)
        return t
        
    def parseEOLStyle(self):
        token = self.token
        maybe_definition = False
        if token[1]==';':
            p=Style(";")
            maybe_definition = True
        elif token[1].startswith(':'):
            p=Style(token[1])
        else:
            p=Style(":")
            
        assert p
        retval = p
        
        self.next()

        last = None
        # search for the newline and replace it with ENDEOLSTYLE
        for idx in range(self.pos, len(self.tokens)-1):
            if self.tokens[idx][0]=='BREAK' or self.tokens[idx][0]=='\n':
                last = idx, self.tokens[idx]
                self.tokens[idx] = ("ENDEOLSTYLE", self.tokens[idx][1])
                break
            
        break_at = TokenSet(['ENDEOLSTYLE', 'BEGINTABLE', 'BREAK', EndTagToken])
        
        while self.left:
            token = self.token
            if token[0] in break_at:
                break
            elif maybe_definition and token[1]==':':
                self.next()
                maybe_definition = False
                retval = Node()
                retval.append(p)
                p = Style(":")
                retval.append(p)
                
            elif token[0] in FirstAtom:
                p.append(self.parseAtom())
            else:
                log.info("in parseEOLStyle: assuming text", token)
                p.append(Text(token[1]))
                self.next()

        if last:
            self.tokens[last[0]] = last[1]

        return retval
            
    def parseParagraph(self):
        p = Node()
                    
        while self.left:
            token = self.token
            if token[0]=='EOLSTYLE':
                p.append(self.parseEOLStyle())
            elif token[0]=='PRE':
                pre = self.parsePre()
                if pre is None:
                    # empty line with spaces. handle like BREAK
                    p.__class__ = Paragraph
                    break            
                p.append(pre)
            elif token[0] == 'BREAK':
                self.next()
                p.__class__ = Paragraph
                break            
            elif token[0] == 'SECTION':
                p.__class__ = Paragraph
                break
            elif token[0] == 'ENDSECTION':
                p.append(Text(token[1]))
                self.next()
            elif token[0] in FirstAtom:
                p.append(self.parseAtom())
            else:
                break

        if not self.left:
            p.__class__ = Paragraph

        if p.children:
            return p
        else:
            return None

    def parseTagToken(self):
        tag = self.token[0].t
        try:
            m=getattr(self, 'parse'+tag.upper()+'Tag')
        except (AttributeError, UnicodeEncodeError):
            t=Text(self.token[1])
            self.next()
            return t
        else:
            return m()

    def parseEMTag(self):
        return self._parseStyledTag(Style("''"))
    
    def parseITag(self):
        return self._parseStyledTag(Style("''"))
        
    def parseBTag(self):
        return self._parseStyledTag(Style("'''"))

    def parseSTRONGTag(self):
        return self._parseStyledTag(Style("'''"))
    
    def parseBLOCKQUOTETag(self):
        return self._parseStyledTag(Style(":"))

    def _parseStyledTag(self, style=None):
            
        token = self.token[0]
        if style is None:
            style = Style(token.t)

        b = style        
        end = EndTagToken(token.t)
        start = TagToken(token.t)
        self.next()

        
        if token.selfClosing:
            return style 
        
        break_at = set(["ENDTABLE", "ROW", "COLUMN", "ITEM", "BREAK", "SECTION", "BEGINTABLE"])
        
        while self.left:
            token = self.token
            if token[0] in break_at:
                break
            elif token[0]=='\n':
                b.append(Text(token[1]))
                self.next()
            elif token[0]==end:
                self.next()
                break
            elif isinstance(token[0], EndTagToken):
                break
            elif isinstance(token[0], TagToken):
                if token[0]==start:
                    self.next()  # 'Nuclear fuel' looks strange otherwise
                    break
                b.append(self.parseTagToken())
            elif token[0] in FirstAtom:
                b.append(self.parseAtom())
            else:
                log.info("_parseStyledTag: assuming text", token)
                b.append(Text(token[1]))
                self.next()

        return b

    parseVARTag = parseCITETag = parseSTag = parseSUBTag = parseBIGTag = parseSMALLTag = _parseStyledTag
    
    def parseBRTag(self):
        token = self.token[0]
        n = TagNode(token.t)
        n.starttext = token.text
        n.endtext = u''
        self.next()
        return n
    
    parseHRTag = parseBRTag

    def parseUTag(self):
        token = self.token
        if "overline" in self.token[1].lower():
            s = Style("overline")
        else:
            s = None
            
        return self._parseStyledTag(s)

    def parsePre(self):
        p = n = PreFormatted()
        token = self.token
        p.append(Text(token[1]))
        
        self.next()

        # find first '\n' not followed by a 'PRE' token
        last = None
        for idx in range(self.pos, len(self.tokens)-1):
            if self.tokens[idx][0] in ['ROW', 'COLUMN', 'BEGINTABLE', 'ENDTABLE', 'TIMELINE', 'MATH']:
                return None
            
            if self.tokens[idx][0]=='BREAK':
                break
            
            if self.tokens[idx][0]=='\n' and self.tokens[idx+1][0]!='PRE':
                last = idx, self.tokens[idx]
                self.tokens[idx]=('ENDPRE', '\n')
                break
        
        
        while self.left:
            token = self.token
            if token[0] == 'ENDPRE' or token[0]=='BREAK':
                break            
            if token[0]=='\n' or token[0]=='PRE' or token[0]=='TEXT':
                p.append(Text(token[1]))
                self.next()
            elif token[0] == 'SPECIAL':
                p.append(Text(token[1]))
                self.next()
            elif isinstance(token[0], EndTagToken):
                break
            elif isinstance(token[0], TagToken):
                if token[0] == tag_div:
                    break
                
                p.append(self.parseTagToken())
            elif token[0] in FirstAtom:
                p.append(self.parseAtom())
            else:
                log.info("in parsePre: assuming text", token)
                p.append(Text(token[1]))
                self.next()

        if last:
            self.tokens[last[0]] = last[1]

        for x in p:
            if not isinstance(x, Text):
                return p
            if x.caption.strip():
                return p
            
        return None
    
    
    
    def parseOLTag(self):
        numbered = parseParams(self.token[1]).get('type', '1')
        return self._parseHTMLList(numbered)

    def parseULTag(self):
        return self._parseHTMLList(False)

    def parseLITag(self):

        p = item = Item()

        p.vlist = parseParams(self.token[1])

        self.next()
        break_at = TokenSet([EndTagToken, 'ENDTABLE', 'SECTION'])
        while self.left:
            token = self.token
            if token[0] == '\n':
                p.append(Text(token[1]))
                self.next()
            elif token[0] == 'EOLSTYLE':
                p.append(self.parseEOLStyle())
            elif token[0]=='BREAK':
                append_br_tag(p)
                self.next()
            elif token[0]==tag_li:
                break
            elif token[0]==EndTagToken("li"):
                self.next()
                break
            elif token[0] in break_at:
                break
            elif token[0] in FirstAtom:
                p.append(self.parseAtom())
            else:
                log.info("in parseLITag: assuming text", token)
                p.append(Text(token[1]))
                self.next()

        return item

        
    def _parseHTMLList(self, numbered):
        lst = ItemList()
        lst.numbered = numbered
        
        end = EndTagToken(self.token[0].t)

        self.next()
        while self.left:
            token = self.token            
            if token[0]==end:
                self.next()
                break
            elif isinstance(token[0], TagToken):
                lst.append(self.parseTagToken())
            elif token[0]=='ITEM':                
                lst.append(self.parseItemList())
            elif token[0] in FirstAtom:
                lst.append(self.parseAtom())
            else:
                log.info("assuming text in _parseHTMLList", token)
                lst.append(Text(token[1]))
                self.next()

        return lst
            
                       
    def parseItemList(self):
        # actually this parses multiple nested item lists..
        items = []
        while self.left:
            token = self.token
            if token[0]=='ITEM':
                items.append(self.parseItem())
            else:
                break

        # hack
        commonprefix = lambda x,y : os.path.commonprefix([x,y])
        
        current_prefix = u''
        stack = [Node()]

        def append_item(parent, node):
            if parent is stack[0]:
                parent.append(node)
                return

            if not parent.children:
                parent.children.append(Item())

            parent.children[-1].append(node)

        for item in items:
            prefix = item.prefix.strip(":")
            common = commonprefix(current_prefix, item.prefix)

            stack = stack[:len(common)+1]

            create = prefix[len(common):]
            for x in create:
                itemlist = ItemList()
                itemlist.numbered = (x=='#')
                append_item(stack[-1], itemlist)
                stack.append(itemlist)
            stack[-1].append(item)
            current_prefix = prefix

        return stack[0]
    
    def parseItem(self):
        p = item = Item()
        p.prefix = self.token[1]

        self.token[1]
        break_at = TokenSet(["ENDTABLE", "COLUMN", "ROW"])
        
        self.next()
        while self.left:
            token = self.token
            
            if token[0] == '\n':
                self.next()
                break
            elif token[0]=='BREAK':
                break
            elif token[0]=='SECTION':
                break
            elif isinstance(token[0], EndTagToken):
                break
            elif token[0] in break_at:
                break
            elif token[0] in FirstAtom:
                p.append(self.parseAtom())
            else:
                log.info("in parseItem: assuming text", token)
                p.append(Text(token[1]))
                self.next()
        return item
    
        
    def parse(self):
        log.info("Parsing", repr(self.name))
        try:
            return self.parseArticle()
        except Exception, err:
            log.error("error while parsing article", repr(self.name), repr(err))
            raise

def main():
    #import htmlwriter
    from mwlib.dummydb import DummyDB
    db = DummyDB()
    
    for x in sys.argv[1:]:
        input = unicode(open(x).read(), 'utf8')
        from mwlib import expander
        te = expander.Expander(input, pagename=x, wikidb=db)
        input = te.expandTemplates()

        
        tokens = tokenize(input, x)
        
        p=Parser(tokens, os.path.basename(x))
        r = p.parse()

        show(sys.stdout, r, 0)
        
        #hw = htmlwriter.HTMLWriter(htmlout)
    
if __name__=="__main__":
    main()
