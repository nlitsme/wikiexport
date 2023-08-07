"""
Author: Willem Hengeveld <itsme@xs4all.nl>

Tool for printing an entire mediawiki site to stdout.
Mediafiles are saved to the directory specified with --savedir

"""
import asyncio
import aiohttp.connector
import aiohttp
import os.path
import html.parser
import urllib.parse
from collections import defaultdict

debug = False

class BaseurlFilter(html.parser.HTMLParser):
    """
    Extracts the mediawiki base url from an html page.
    """
    def __init__(self):
        super().__init__()
        self.baseurl = defaultdict(int)
        self.stack = []
        self.caphreflevel = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("meta", "input", "br", "link", "img", "hr"):
            return self.handle_startendtag(tag, attrs)
        self.stack.append(tag)

        d = dict(attrs)

        # set new captures
        if tag == 'li' and d.get('id') in ('pt-login', 'ca-viewsource', 't-print', 'ca-history', 't-permalink'):
            self.caphreflevel = len(self.stack)
        elif tag == 'a':
            if self.caphreflevel or d.get('id') in ('pt-login', 'ca-viewsource', 't-print', 'ca-history', 't-permalink'):
                url = d.get('href')
                self.baseurl[url[:url.find('?')]] += 1

    def handle_endtag(self, tag):
        # clean up captures
        if self.caphreflevel == len(self.stack):
            self.caphreflevel = 0

        # clean up stack
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            for i, e in reversed(list(enumerate(self.stack))):
                if e==tag:
                    print("missing end tag for:", self.stack[i+1:], "closing", self.stack[i:i+1])
                    while len(self.stack)>i:
                        self.stack.pop()
                    return
            print("could not find start tag for: '%s' in %s" % (tag, self.stack))


    def handle_startendtag(self, tag, attrs):
        d = dict(attrs)

    def handle_data(self, data):
        pass


def ExtractBaseurl(html):
    """
    Finds wiki baseurl on html page
    """
    try:
        parser = BaseurlFilter()
        parser.feed(html)
    finally:
        parser.close()

    if len(parser.baseurl)>1:
        print("baseurl: found multiple", parser.baseurl)
    if len(parser.baseurl)==0:
        raise Exception("no baseurl found")

    return max(parser.baseurl.items(), key=lambda kv:kv[1])[0]


async def findbaseurl(loop, page):
    """
    Downloads the specified page, and extracts the wiki's baseurl from it.
    """
    async with aiohttp.ClientSession(loop=loop) as client:
        req = await client.get(page)
        uri = urllib.parse.urljoin(page, ExtractBaseurl(await req.text()))
    return uri


class NamespacesFilter(html.parser.HTMLParser):
    """
    Parser object for extracting the list of namespaces from an html page.
    """
    def __init__(self):
        super().__init__()
        self.baseurl = defaultdict(int)
        self.stack = []
        self.caplevel = 0
        self.capdata = None
        self.capvalue = None

        self.namespaces = []

    def handle_starttag(self, tag, attrs):
        if tag in ("meta", "input", "br", "link", "img", "hr"):
            return self.handle_startendtag(tag, attrs)
        self.stack.append(tag)

        d = dict(attrs)

        # set new captures
        if tag == 'select' and d.get('id') == 'namespace':
            self.caplevel = len(self.stack)
            self.capdata = ''
        elif self.caplevel and tag == 'option':
            self.capdata = ''
            self.capvalue = int(d.get('value'),10)

    def handle_endtag(self, tag):
        # clean up captures
        if self.caplevel == len(self.stack):
            self.caplevel = 0
        elif self.caplevel and tag=='option':
            self.namespaces.append((self.capvalue, self.capdata))

        # clean up stack
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            for i, e in reversed(list(enumerate(self.stack))):
                if e==tag:
                    print("missing end tag for:", self.stack[i+1:], "closing", self.stack[i:i+1])
                    while len(self.stack)>i:
                        self.stack.pop()
                    return
            print("could not find start tag for:", tag, "in", self.stack)


    def handle_startendtag(self, tag, attrs):
        pass

    def handle_data(self, data):
        if self.caplevel:
            self.capdata += data


def ExtractNamespaces(html):
    """
    Extract the list of namespaces from an html page.
    """
    try:
        parser = NamespacesFilter()
        parser.feed(html)
    finally:
        parser.close()

    return parser.namespaces

class AllpagesFilter(html.parser.HTMLParser):
    """
    Parser object for extracting the list of wiki pagenames from an AllPages html output.
    """
    def __init__(self):
        super().__init__()
        self.allpageslist = []
        self.pagelist = []
        self.nextpage = None
        self.stack = []
        self.allcaplevel = 0
        self.pgcaplevel = 0
        self.licaplevel = 0
        self.nncaplevel = 0
    def __repr__(self):
        return "apl=%d, pagelist=%d, s=%d, next='%s', levels: allcap=%d, pgcap=%d, licap=%d, nncap=%d" % (
                len(self.allpageslist),
                len(self.pagelist),
                len(self.stack),
                self.nextpage,
                self.allcaplevel,
                self.pgcaplevel,
                self.licaplevel,
                self.nncaplevel,
                )

    def handle_starttag(self, tag, attrs):
        if tag in ("meta", "input", "br", "link", "img", "hr"):
            return self.handle_startendtag(tag, attrs)
        self.stack.append(tag)

        d = dict(attrs)

        # set new captures
        if tag == 'ul' and d.get('class') == 'mw-allpages-chunk':
            self.licaplevel = len(self.stack)
        elif tag == 'div' and d.get('class') == 'mw-allpages-nav':
            self.nncaplevel = len(self.stack)
        elif tag == 'table':
            cls = d.get('class')
            if cls == 'allpageslist':
                self.allcaplevel = len(self.stack)
            elif cls == 'mw-allpages-table-chunk':
                self.pgcaplevel = len(self.stack)
        elif tag == 'a':
            if self.allcaplevel:
                uri = urllib.parse.urlparse(d.get('href'))
                qs = urllib.parse.parse_qs(uri.query)
                pair = (qs['from'][0], qs['to'][0])
                if not self.allpageslist or self.allpageslist[-1] != pair:
                    self.allpageslist.append(pair)
            elif self.pgcaplevel:
                self.pagelist.append(d.get('title'))
            elif self.licaplevel:
                self.pagelist.append(d.get('title'))
            elif self.nncaplevel:
                uri = urllib.parse.urlparse(d.get('href'))
                qs = urllib.parse.parse_qs(uri.query)
                self.nextpage = qs['from'][0]
                if debug:
                    print("next: %s" % self.nextpage)

    def handle_endtag(self, tag):
        # clean up captures
        if self.allcaplevel == len(self.stack):
            self.allcaplevel = 0
        if self.pgcaplevel == len(self.stack):
            self.pgcaplevel = 0
        if self.nncaplevel == len(self.stack):
            self.nncaplevel = 0
        if self.licaplevel == len(self.stack):
            self.licaplevel = 0

        # clean up stack
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            for i, e in reversed(list(enumerate(self.stack))):
                if e==tag:
                    print("missing end tag for:", self.stack[i+1:], "closing", self.stack[i:i+1])
                    while len(self.stack)>i:
                        self.stack.pop()
                    return
            print("could not find start tag for:", tag, "in", self.stack)

    def handle_startendtag(self, tag, attrs):
        pass


def ExtractAllPages(html):
    """
    Extract the list of wiki pagenames from an AllPages html output.
    """
    if debug:
        print("extract all pages, htmlsize=%d" % len(html))
    try:
        parser = AllpagesFilter()
        parser.feed(html)
    finally:
        parser.close()

    return parser

class MediaWiki:
    """
    object for talking to a mediawiki server.
    """
    def __init__(self, loop, baseurl, args):
        self.baseurl = baseurl

        moreargs = {}
        if args.limit:
            moreargs["connector"] = aiohttp.connector.TCPConnector(limit=args.limit)

        hdrs = dict(Referer=baseurl)
        hdrs["User-Agent"] = "Mozilla/6.0 (Windows; U; Windows NT 6.0; en-US) Gecko/2009032609 (KHTML, like Gecko) Chrome/2.0.172.6 Safari/530.7"

        self.client = aiohttp.ClientSession(loop=loop, headers=hdrs, **moreargs)
        self.cookies = []

    def __del__(self):
        if self.client:
           asyncio.get_event_loop().create_task(self.client.close())

    def get(self, params, path=""):
        """
        Do a HTTP GET request
        """
        return self.client.get(self.baseurl+path, params=params)

    def post(self, form):
        """
        Do a HTTP POST request
        """
        return self.client.post(self.baseurl, data=aiohttp.FormData(form))

    async def savefile(self, name, fh):
        """
        Save the binary file to <fh>
        """
        try:
            resp = await self.get({'title':'Special:Redirect/file/'+name})
            while True:
                chunk = await resp.content.read(0x10000)
                if not chunk:
                    break
                fh.write(chunk)
        finally:
            resp.close()
            fh.close()

    async def namespaces(self):
        """
        Get list of namespaces from the wiki.
        """
        try:
            resp = await self.get({'title':'Special:PrefixIndex'})
            ns = ExtractNamespaces(await resp.text())
        finally:
            resp.close()
        return ns

    async def allpages(self, ns, frm = None, unt = None):
        """
        Generator which generates all page names on the wiki.
        This function can call itself recursively.
        """
        while True:
            if debug:
                print("allpages, ns:'%s', frm:'%s'" % (ns, frm))
            d = {'title':'Special:AllPages', 'namespace':ns}
            if frm:
                d['from'] = frm
            if unt:
                d['to'] = unt
            resp = None
            try:
                resp = await self.get(d)
                allpg = ExtractAllPages(await resp.text())
                if debug:
                    print("from '%s' -> %s" % (frm, repr(allpg)))
            except Exception as e:
                print("error", e)
                if debug:
                    raise
                return
            finally:
                if resp:
                    resp.close()

            if allpg.allpageslist:
                for frm, unt in allpg.allpageslist:
                    async for pg in self.allpages(ns, frm, unt):
                        yield pg
                break
            else:
                for pg in allpg.pagelist:
                    yield pg
                if not allpg.nextpage:
                    break
                if frm and frm > allpg.nextpage:
                    if debug:
                        print("going back .....")
                    break
                frm = allpg.nextpage
                unt = None


    async def export(self, pages, curonly=True):
        """
        Request the XML export for the list of pages.
        """
        print("export %d pages, curonly=%s" % (len(pages), curonly))
        d = {'title':'Special:Export', 'action':'submit', 'pages':"\n".join(pages)}
        if curonly:
            d['curonly'] = 'true'
        try:
            resp = await self.post(d)
            xml = await resp.read()
        finally:
            resp.close()
        return xml

    async def exportpage(self, pagename):
        """
        Export a single page as XML.
        """
        print("export single page: %s" % (pagename))
        try:
            resp = await self.get({}, "/Special:Export/%s" % urllib.parse.quote(pagename, safe=''))
            xml = await resp.read()
        finally:
            resp.close()
        return xml


    async def pagenames(self):
        """
        Yields all page names from all namespaces
        """
        for nsid, nsname in await self.namespaces():
            async for pg in self.allpages(nsid):
                yield pg


# note about image paths:
#    <basepath> + <hashpath> + <filename>

# h = md5(filename)
# where hashpath = h[:1] + '/' + h[:2]
#       basepath = 

async def exportsite(loop, somepage, args):
    """
    Top level function handling the xml wiki export.
    """
    baseurl = await findbaseurl(loop, somepage)

    print("Using baseurl = %s" % (baseurl))

    wiki = MediaWiki(loop, baseurl, args)

    downloads = []
    pglist = []
    async for pg in wiki.pagenames():
        pglist.append(pg)
        if args.savedir and pg.startswith("File:"):
            filename = pg[5:]
            if filename.find('/')<0:
                downloads.append(wiki.savefile(filename, open(os.path.join(args.savedir, filename), "wb")))
            else:
                print("will not download filenames with slashes: %s" % filename)
        if len(pglist)==args.batchsize:
            if args.batchsize==1:
                downloads.append(wiki.exportpage(pglist[0]))
            else:
                downloads.append(wiki.export(pglist, curonly=not args.history))
            pglist = []
    if pglist:
        # add remaining to export
        downloads.append(wiki.export(pglist, curonly=not args.history))
        pglist = []
    #done, pending = await asyncio.wait(downloads)
    for d in downloads:
        d = await d
        if d:
            # output the xml data to stdout
            print(d.decode('utf-8', 'ignore'))

            # todo: if download failed -> retry

def main():
    import argparse
    parser = argparse.ArgumentParser(description='print entire contents of a mediawiki site in XML format')
    parser.add_argument('--history', action='store_true', help='Include history in export')
    parser.add_argument('--savedir', type=str, help='Save all files to the specified directory')
    parser.add_argument('--limit', type=int, help='Maximum number of simultaneous connections to use.')
    parser.add_argument('--batchsize', type=int, help='Nr of pages to export per request.', default=300)
    parser.add_argument('--debug', action='store_true', help='errors print stacktrace, and abort')
    parser.add_argument('wikipage', type=str)
    args = parser.parse_args()

    global debug
    debug = args.debug

    loop = asyncio.get_event_loop()
    tasks = [ exportsite(loop, args.wikipage, args)  ]
    loop.run_until_complete(asyncio.gather(*tasks))

if __name__ == '__main__':
    main()

