"""
Author: Willem Hengeveld <itsme@xs4all.nl>

Tool for extracting properties from a list of pages, and output them
in a table.

python3 wikiinfo --pages "Venus,Mars,Mercury,Earth" --properties "
"""
import re

def parsehtml(token):
    m = re.match(r'<(\w+)(.*?)/?>', token)
    if m:
        return m.group(1), m.group(2)
    print("ERROR invalid html: %s" % token)

class WikiParser:
    """
    {{command | ... }}
    {{{...}}}
    [[pagename | ... ]]
    [externallink description]
    <tag>...</tag>
    <element key=value ... />
    {|  ... |}   -- table

    <!-- ... -->
    """

    class WikiTable:
        """
        {| ... |}
        """
        def __init__(self, contents):
            self.contents = contents
        def matches(self, token):
            return False
        def __repr__(self):
            return "Table: {| %s |}" % self.contents

    class WikiItem:
        """
        {{{ ... }}}
        """
        def __init__(self, token, contents):
            self.token = token
            self.contents = contents
        def matches(self, token):
            return False
        def inversetoken(self):
            if self.token.startswith("{"):
                return "}" * len(self.token)
            if self.token.startswith("["):
                return "]" * len(self.token)
            return "???"
        def __repr__(self):
            return "Wiki: %s %s %s" % (self.token, self.contents, self.inversetoken())

    class HtmlTag:
        """
        <tag k=v ...>
        """
        def __init__(self, tag, attr):
            self.tag = tag
            self.attr = attr

        def matches(self, token):
            return re.match(r'</\s*%s\s*>' % self.tag, token) is not None
        def __repr__(self):
            return "Html: <%s %s>" % (self.tag, self.attr)

    class HtmlElem:
        """
        <tag k=v />
        or
        <tag k=v > ... </tag>
        """
        def __init__(self, tag, attr, data = None):
            self.tag = tag
            self.attr = attr
            self.data = data

        def matches(self, token):
            return False
        def __repr__(self):
            return "Html: <%s %s>%s</%s>" % (self.tag, self.attr, self.data, self.tag)

    class Open:
        """
        {, {{, {{{, [, [[, {|
        """
        def __init__(self, token):
            self.token = token
        def matches(self, token):
            if self.token == "{|" and token == "|}":
                return True
            if len(self.token) > len(token):
                return False
            if self.token.startswith("{") and token.startswith("}"):
                return True
            if self.token.startswith("[") and token.startswith("]"):
                return True
            return False
        def __repr__(self):
            return "Open: %s" % (self.token)

    class WikiData:
        def __init__(self, data):
            self.data = data
        def matches(self, token):
            return False
        def __repr__(self):
            return "Data: %s" % (self.data.encode('utf-8'))

    class Comment:
        def __init__(self, data):
            self.data = data
        def matches(self, token):
            return False
        def __repr__(self):
            return "Comment: %s" % (self.data)

    def __init__(self):
        self.stack = []
    def feed(self, text):
        M = re.compile(r'{\| | \|}+ | \[+ | \]+ | {+ | }+ | <!--.*?--> | </?\w+[^>]*>', flags=re.X|re.S)
        o = 0
        while o < len(text):
            m = M.search(text, o)
            if not m:
                self.stack.append(self.WikiData(text[o:]))
                break
            if o < m.start():
                self.stack.append(self.WikiData(text[o:m.start()]))
            token = m.group(0)
            o = m.end()
            if token == "{|":
                self.stack.append(self.Open(token))
            elif token == "|}}":
                if isinstance(self.stack[-1], self.WikiData):
                    self.stack[-1].data += "|"
                wikiitem = self.close("}}")
                if wikiitem:
                    self.stack.append(self.WikiItem(wikiitem[0].token, wikiitem[1:]))
                else:
                    print("ERROR: no close1 | }} at %d - %s :  %s" % (o, token, text[o-16:o+16].encode('utf-8')))
            elif token == "|}":
                table = self.close(token)
                self.stack.append(self.WikiTable(table))
            elif token.startswith("{") or token.startswith("["):
                self.stack.append(self.Open(token))
            elif token.startswith("}") or token.startswith("]"):
                # these should all work:
                #   { {  }}   
                #   {{{  }}}
                #   {{ {{  }}}}
                #   {{  {  }}}
                # --> find most recent opening bracket, and close it with the right mount of closing brackets.
                while token:
                    wikiitem = self.close(token)
                    if not wikiitem:
                        print("ERROR - no close for '%s' at %d: %s" % (token, o, text[o-16:o+16].encode('utf-8')))
                        break
                    opentoken = wikiitem[0].token
                    self.stack.append(self.WikiItem(wikiitem[0].token, wikiitem[1:]))
                    token = token[len(opentoken):]

            elif token.startswith("</"):
                htmlelem = self.close(token)
                if htmlelem:
                    htmlopen = htmlelem[0]
                    htmlcontent = htmlelem[1:]
                    self.stack.append(self.HtmlElem(htmlopen.tag, htmlopen.attr, htmlcontent))
                else:
                    print("ERROR - no close for '%s' at %d: %s" % (token, o, text[o-32:o+32].encode('utf-8')))
            elif token.startswith("<!--"):
                self.stack.append(self.Comment(token))
            elif token.startswith("<") and token.endswith("/>"):
                tag, attr = parsehtml(token)
                self.stack.append(self.HtmlElem(tag, attr))
            elif token.startswith("<") and token.endswith(">"):
                tag, attr = parsehtml(token)

                # special handling for <math>, <nowiki>, <noinclude>
                if tag in ('math', 'nowiki', 'noinclude'):
                    ET = re.compile(r'</\s*%s\s*>' % tag)
                    m = ET.search(text, o)
                    if not m:
                        print("ERROR - expected </%s> after %d" % (tag, o))
                    else:
                        self.stack.append(self.HtmlElem(tag, attr, text[o:m.start()]))
                        o = m.end()
                else:
                    self.stack.append(self.HtmlTag(tag, attr))

            else:
                print("Unknown token: %s" % token)

    def close(self, token):
        """
        returns enclosed items.
        or None when no opening bracket found.
        """
        popped = []
        while self.stack:
            item = self.stack.pop()
            popped.append(item)
            if item.matches(token):
                return popped[::-1]
        self.stack = popped[::-1]


def parseWikitext(wikitext):
    w = WikiParser()
    w.feed(wikitext.decode('utf-8'))

    return w.stack

def findTemplate(tree, templatename):
    for item in tree:
        if isinstance(item, WikiParser.WikiItem):
            if isinstance(item.contents[0], WikiParser.WikiData):
                n = item.contents[0].data.split(" ")
                if n[0] == templatename:
                    return item.contents

def parseInfobox(ibox):
    """
    {{Infobox boxname
    | propname = {{plainlist | {{val | <value> }} }}
    }}

    returns a dictionary of key/value pairs
    """
    records = []

    def addtext(txt):
        if type(records[-1][-1]) == str:
            # join consequetive string items.
            records[-1][-1] += txt
        else:
            records[-1].append(txt)

    for item in ibox:
        if isinstance(item, WikiParser.WikiData):
            f = item.data.split("|")
            if item.data[:1] != "|" and records:
                addtext(f[0])
                del f[0]
            for x in f:
                records.append([x])
        elif isinstance(item, WikiParser.WikiItem) \
              or isinstance(item, WikiParser.HtmlElem):
            records[-1].append(item)
        else:
            # .. todo: ignore comment
            #print("??? - %s" % item)
            pass

    d = dict()
    for rec in records:
        m = re.match(r'^\s*(\w+)\s*=\s*(.*)', rec[0])
        if not m:
            # todo: ignore infobox header
            #print("!!! - %s" % rec)
            pass
        else:
            k = m.group(1)
            v0 = m.group(2)
            rec[0] = v0
            if not v0:
                del rec[0]
            d[k] = rec

    #for k, v in d.items():
    #    print("\t%-30s\t%s" % (k, v))
    return d

def extractValue(valuelist):
    if not valuelist:
        return
    for item in valuelist:
        if isinstance(item, WikiParser.WikiItem) and item.token == "{{":
            v = extractValue(item.contents)
            if v:
                return v
        elif isinstance(item, WikiParser.WikiData):
            base = None
            exponent = 0
            accuracy = None
            isvalue = None
            for fld in item.data.split('|'):
                if not fld:
                    continue
                if fld == 'val':
                    isvalue = True
                elif fld.startswith('fmt='):
                    pass
                elif isvalue:
                    m = re.match(r'^(\w+)\s*=\s*(\S*)', fld)
                    if m:
                        if m.group(1) == 'e':
                            exponent = int(m.group(2))
                        elif m.group(1) in ('u', 'ul'):
                            unit = m.group(2)
                        else:
                            print("unknown value property: %s" % fld)
                    elif base is None:
                        base = float(fld)
                    elif accuracy is None:
                        accuracy = float(fld)
                    else:
                        print("value:", fld)
            if isvalue:
                return base * pow(10, exponent)
    return 

def getpage(language, pagename):
    import urllib.request
    import urllib.parse

    req = urllib.request.Request("https://%s.wikipedia.org/wiki/" % language + urllib.parse.quote(pagename) + "?action=raw")
    response = urllib.request.urlopen(req)
    return response.read()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Extract tables of information from wikipedia.')
    parser.add_argument('--language', '-l', type=str, help='Which wikipedia site to use.', default='en')
    parser.add_argument('--pages', '-p', type=str, help='Which pages to search.')
    parser.add_argument('--properties', '-q', type=str, help='Which properties to extract.')
    args = parser.parse_args()

    for pg in args.pages.split(","):
        print("==>", pg, "<==")
        try:
            wikitext = getpage(args.language, pg)
            tree = parseWikitext(wikitext)
            ibox = findTemplate(tree, "Infobox")

            props = parseInfobox(ibox)
            for p in args.properties.split(","):
                print(extractValue(props.get(p)), end="\t")
            print()
        except Exception as e:
            print(e)
            import traceback
            traceback.print_exc()

        print()

if __name__ == '__main__':
    main()

