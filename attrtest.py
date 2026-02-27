class Test:
    def __setattr__(self, name, value):
        print("setattr called!", name, value)
        self.__dict__[name] = value

t = Test()
print(dir(t))
t.abc = 123               # should print the message
print(t.abc)              # 123