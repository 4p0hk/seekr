![seekr logo](docs/logo.png)
# seekr
## about the app
seekr is a tool that helps you figure out which tracks from your playlist on a streaming service exist either in your computer's music folder, or in rekordbox.

- when you have a playlist worth of music on your stream service, this bridges the gap between the service and your collection.
- the alternative is  manually searching for every track to see what you already have vs. what you're missing, avoiding duplicates.

tested and working with rekordbox v7.2 on windows 11. macOS coming soon

## how it works
1. use soundiiz.com to connect your streaming service
2. find your playlist in soundiiz, click the three dots menu, choose "Export as a File > Export to json"
3. seekr.py takes the .json, reads your rekordbox database and searches the folder you give it to find each track
4. seekr.py creates reports telling you what is where

once the python resources are setup, it's usage is simply:
``` 
seekr.py -i tracks.json -d Z:\\media --score 80 -dllist
```

# first time setup
a bootstrap script takes care of setting the venv, loading dependencies

1. download the repo from github
2. keep setup.ps1 and seekr.py in the same folder
3. run setup.ps1 to prepare the assets that seekr.py relies on

now you're ready to use seekr

# using the app
## scan your playlist
### 1. download it from soundiiz
- login/setup soundiiz, find your playlist, click the "..." menu
- select the option "Export to a FIle", choose JSON
- move that file next to seekr.py to make it easy

### 2. run seekr.py
feed it: -i, -d, --score
optionally: --report and --dllist

- *-i tracks.json*: this is the json file created by soundiiz.com of your playlist from any service
- *-d Z:\\media\\audio\\music\\dj-library*: this is where you store your music, use double slashes to escape based on your shell
- *--score 80*: this controls the algorithm, play with it and see the results. more on this below
- *--report*: this tells seekr to output a .csv report of its findings, all of them
- *--dllist*: another .csv report only showing the tracks you're missing so you have a checklist while shopping

```
python seekr.py -i tracks.json -d Z:\\media --score 80 --report --dllist
```
*or*
```
python seekr.py -i tracks.json -d Z:\\media --score 80 --dllist
```
*or*
```
python seekr.py -i tracks.json -d Z:\\media --score 80
```

reports are saved next to the seekr.py script, if you chose to print them

# appendix
## quirks
- the algorithm tries to strip stuff but it is not perfect
- stuff with symbols will be hard as it's not always the same from system to system
- this also goes for features, multi artist collabs, etc
- sanity check those manualy when it tells you they're missing 

with regular stuff like "linkin park - in the end" in the ID tag, it will work flawlessly as long as the fields are clean. 

things like "linkin park - in the end {emo4lyf}" or "ft mike shinoda" in the ID tag will likely cause mismatch as it lowers the score of the match..

## score explained in detail
we use rapidfuzz’s fuzz.token_set_ratio(a, b)

- it splits your search string (needle) and the target (text) into tokens (words), then compares the intersection/union of those sets
- score is a number 0–100, where 100 means an exact token match (same words), 0 means no overlap
- setting --score X means we only keep matches ≥ X
- lower X -> more “loose” matches (even partial or out-of-order words)
- higher X -> stricter (tokens must align closely)

> so if you see score=91, ~91% token similarity. 

tweak that threshold to widen or narrow your results.