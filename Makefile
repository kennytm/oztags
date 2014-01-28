bin/oztags: oztags.py
	cp $< $@

clean:
	rm -f bin/oztags

.PHONY: clean

