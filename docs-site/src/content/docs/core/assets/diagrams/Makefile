# Render semantic .dot diagrams to *-light.webp and *-dark.webp using Luminous Graphviz.
THEME   ?= ../../../../../../../../graphviz-style/theme/luminous.gvpr
SOURCES := $(wildcard *.dot)
WEBP    := $(foreach t,light dark,$(SOURCES:.dot=-$(t).webp))
PNG     := $(WEBP:.webp=.png)
SVG     := $(WEBP:.webp=.svg)

GVPR ?= gvpr
DOT  ?= dot

.PHONY: all webp png svg clean
all: webp
webp: $(WEBP)
png:  $(PNG)
svg:  $(SVG)

define render
%-$(1).$(2): %.dot
	$$(GVPR) -c -f $$(THEME) -a $(1) $$< | $$(DOT) -T$(2) -o $$@
endef
$(foreach t,light dark,$(foreach f,webp png svg,$(eval $(call render,$(t),$(f)))))

clean:
	rm -f *.webp *.png *.svg
