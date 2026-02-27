# NOTE currently assumes the object lists won't change in between saving and loading

def save_object_settings(voicelist, adsrlist, lfolist):

    todo = voicelist + adsrlist + lfolist

    with open("SETTINGS", "w") as f:
        for obj in todo:
            settings_ls = obj.export()
            for q in settings_ls:
                f.write(str(q))
                f.write(" ")
            f.write("\n")

def load_object_settings(voicelist, adsrlist, lfolist):

    todo = voicelist + adsrlist + lfolist
    index = 0

    with open("SETTINGS", "r") as f:
        for line in f.readlines():
            ls = line.rstrip("\n").split(" ")[:-1]  # we will always get an empty string at the end because of
            # splitting on spaces, consistent, so just discard it
            #print(ls)
            todo[index].load([int(q) for q in ls])  # settings are always 8-bit numbers
            index += 1