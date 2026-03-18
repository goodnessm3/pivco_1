# NOTE currently assumes the object lists won't change in between saving and loading

def save_object_settings(voicelist, adsrlist, lfolist):

    todo = [voicelist[0]] + adsrlist + lfolist
    # consider all voices the same for now

    with open("SETTINGS", "w") as f:
        for obj in todo:
            settings_ls = obj.export()
            for q in settings_ls:
                f.write(str(q))
                f.write(" ")
            f.write("\n")

def load_object_settings(voicelist, adsrlist, lfolist):

    first_pass = True
    todo = voicelist + adsrlist + lfolist
    index = 0

    with open("SETTINGS", "r") as f:
        for line in f.readlines():
            if line == "\n":
                break  # end of file
            ls = line.rstrip("\n").split(" ")[:-1]  # we will always get an empty string at the end because of
            # splitting on spaces, consistent, so just discard it
            #print(ls)
            if first_pass:
                for _ in voicelist:  # read the same line for each voice, right now they are all the same
                    todo[index].load([int(q) for q in ls])  # settings are always 8-bit numbers
                    index += 1
                first_pass = False
                continue

            todo[index].load([int(q) for q in ls])  # settings are always 8-bit numbers
            index += 1