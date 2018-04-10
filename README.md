mediawiki
==========

Tool for exporting the entire contents of a mediawiki site in XML format.
This tool needs python3.

This tool finds all wiki namespaces ( such as User, Talk, etc ), and for each namespace then
proceeds to download all pages. `wikiexport` can also download all binary files found on the wiki.


OPTIONS
=======

 * `--history`  include history in the export.
 * `--savedir DIR`  save binary files to directory `DIR`.
 * `--limit NUM`  specify maximum simultaneous downloads.
 * `--batchsize NUM` specify the number of pages to download in one batch.

EXAMPLE
=======

    python3 mediawiki.py  https://yourwiki.com/Mainpage


BUGS
====

This does not work with all mediawiki sites, variation between sites can be quite large.
Also some sites implement some kind of rate limiting, which causes the site to reject
requests from this tool.


AUTHOR
======

Willem Hengeveld <itsme@xs4all.nl>

