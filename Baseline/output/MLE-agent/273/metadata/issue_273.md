```
Traceback(most recent call last):

File "/Users/zachkoo/miniconda3/envs/mle/bin/mle", line 33, in <module>sys exit(load_entry_point('mle-
agent','console_scripts','mle')())File "/Users/zachkoo/miniconda3/envs/mle/bin/mle", line 25, in 
importlib_load_entry_pointo return next(matches).load()File 
"/Users/zachkoo/miniconda3/envs/mle/lib/python3.9/importlib/metadata.py", line 86, in loadmodule =import 
module(match.group("module'))File "/Users/zachkoo/miniconda3/envs/mle/lib/python3.9/importlib/_init_.py", line 127, in 
import_moduleYesreturn bootstrap._gcd_import(name[level:], package, level)File "<frozen importlib.sbootstrap>"line 
1030,in gcd importFile "<frozen importlib. bootstrap>"line 1007,in find_and loadline 986,in find_and load_unlockedFile,"
<frozenimportlib.. bootstrap>File "<frozen importlib. bootstrap>".line 680,in load unlocked.File "<frozen importlib..
 bootstrap_external>",line 850,in exec moduleFileg""<frozen importlib.bootstrap>",line 228,in 
call_with_frames_removedFile "/Users/zachkoo/Desktop/MLE-agent/mle/cli.py", line 26, in 
<module>memory=LanceDBMemory(os.getcwd())File "/Users/zachkoo/Desktop/MLE-agent/mle/utils/memory.py",line 23,in_init
if config["platform"]-*OpenAI":
TypeError:'NoneType'object is not subscriptable
```