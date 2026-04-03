PREFIX ?= /usr/local
BINDIR := $(PREFIX)/bin

.PHONY: install uninstall

install:
	install -Dm755 hypr-scroll-indicator $(DESTDIR)$(BINDIR)/hypr-scroll-indicator
	install -Dm755 hypr-scroll-indicator.py $(DESTDIR)$(BINDIR)/hypr-scroll-indicator.py

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/hypr-scroll-indicator
	rm -f $(DESTDIR)$(BINDIR)/hypr-scroll-indicator.py
