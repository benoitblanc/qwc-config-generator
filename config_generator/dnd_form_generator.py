import os
import psycopg2
from xml.etree import ElementTree


class DnDFormGenerator:
    def __init__(self, logger, qwc_base_dir):
        self.logger = logger
        self.qwc_base_dir = qwc_base_dir

    def generate_form(self, maplayer, layername):
        attributeEditorForm = maplayer.find('attributeEditorForm')
        if not attributeEditorForm:
            return None

        aliases = {}
        for entry in maplayer.find('aliases').findall('alias'):
            field = entry.get('field')
            alias = entry.get('name')
            aliases[field] = alias or field

        ui = ElementTree.Element("ui")
        ui.set("version", "4.0")

        widget = ElementTree.Element("widget")
        widget.set("class", "QWidget")
        ui.append(widget)

        self.__add_container_fields(maplayer, widget, attributeEditorForm, aliases)

        text = ElementTree.tostring(ui, 'utf-8')
        outputdir = os.path.join(self.qwc_base_dir, 'assets', 'forms', 'autogen')
        try:
            os.makedirs(outputdir, exist_ok=True)
            outputfile = os.path.join(outputdir, layername + ".ui")
            with open(outputfile, "wb") as fh:
                fh.write(text)
                self.logger.info("Wrote %s.ui" % layername)
        except Exception as e:
            self.logger.warning("Failed to write form for layer %s: %s" % (layername, str(e)))
            return None

        return ":/forms/autogen/%s.ui" % layername

    def __add_widget_property(self, widget, name, valueEl, key, defaultValue="", propClass="property", valueClass="string"):
        property = ElementTree.Element(propClass)
        property.set("name", name)
        string = ElementTree.Element(valueClass)
        if valueEl is not None:
            string.text = valueEl.get(key)
        else:
            string.text = defaultValue
        property.append(string)
        widget.append(property)

    def __create_editor_widget(self, maplayer, field):
        editWidget = maplayer.find("fieldConfiguration/field[@name='%s']/editWidget" % field)
        if editWidget.get("type") == "Hidden":
            return None

        widget = ElementTree.Element("widget")
        widget.set("name", field)

        if editWidget.get("type") == "TextEdit":
            optMultiline = editWidget.find("config/Option/Option[@name='IsMultiline']")
            className = "QLineEdit"
            if optMultiline is not None and optMultiline.get("value") == True:
                className = "QTextEdit"
            widget.set("class", className)
            return widget
        elif editWidget.get("type") == "Range":
            optMin = editWidget.find("config/Option/Option[@name='Min']")
            optMax = editWidget.find("config/Option/Option[@name='Max']")
            optStep = editWidget.find("config/Option/Option[@name='Step']")
            optStyle = editWidget.find("config/Option/Option[@name='Style']")
            className = "QSpinBox"
            if optStyle is not None and optStyle.get("value") == "Slider":
                className = "QSlider"
                self.__add_widget_property(widget, "orientation", None, None, "Qt::Horizontal", "property", "enum")
            widget.set("class", className)
            self.__add_widget_property(widget, "minimum", optMin, "value", "-2147483648")
            self.__add_widget_property(widget, "maximum", optMax, "value", "2147483647")
            self.__add_widget_property(widget, "singleStep", optStep, "value", "1")
            return widget
        elif editWidget.get("type") == "DateTime":
            optFormat = editWidget.find("config/Option/Option[@name='display_format']")
            widget.set("class", "QDateTimeEdit")
            self.__add_widget_property(widget, "displayFormat", optFormat, "value", "yyyy-MM-dd")
            return widget
        elif editWidget.get("type") == "CheckBox":
            widget.set("class", "QCheckBox")
            return widget
        elif editWidget.get("type") == "ValueMap":
            optMap = editWidget.findall("config/Option/Option[@name='map']/Option")
            widget.set("class", "QComboBox")
            if optMap is not None:
                for opt in optMap:
                    child = opt.find("Option")
                    if child is not None:
                        item = ElementTree.Element("item")
                        self.__add_widget_property(item, "value", child, "value")
                        self.__add_widget_property(item, "text", child, "name")
                        widget.append(item)
            return widget
        elif editWidget.get("type") == "ValueRelation":
            key = editWidget.find("config/Option/Option[@name='Key']").get('value')
            value = editWidget.find("config/Option/Option[@name='Value']").get('value')
            source = editWidget.find("config/Option/Option[@name='LayerSource']").get('value')
            source_params = dict(map(lambda x: x.split("="), source.split(" ")))
            query = "SELECT %s, %s FROM %s" % (key, value, source_params["table"])

            widget.set("class", "QComboBox")
            try:
                conn = psycopg2.connect("service=%s" % source_params["service"])
                cur = conn.cursor()
                cur.execute(query)
                for row in cur.fetchall():
                    item = ElementTree.Element("item")
                    self.__add_widget_property(item, "value", None, None, row[0])
                    self.__add_widget_property(item, "text", None, None, row[1])
                    widget.append(item)

            except Exception as e:
                self.logger.warning("Failed to read value relations: %s" % str(e))
                return None
            return widget
        else:
            self.logger.warning("Warning: unhandled widget type %s" % editWidget.get("type"))
            return None

    def __add_container_fields(self, maplayer, parent, container, aliases):

        layout = ElementTree.Element("layout")
        layout.set("class", "QGridLayout")
        parent.append(layout)

        tabWidget = None
        row = 0
        col = 0
        ncols = int(container.get('columnCount', '1'))

        for child in container:
            if child.tag == "attributeEditorContainer":
                item = ElementTree.Element("item")
                item.set("row", str(row))
                item.set("column", str(col))
                item.set("colspan", "2")
                layout.append(item)

                if child.get('groupBox') == "0":
                    if not tabWidget:
                        tabWidget = ElementTree.Element("widget")
                        tabWidget.set("class", "QTabWidget")
                        item.append(tabWidget)

                    widget = ElementTree.Element("widget")
                    widget.set("class", "QWidget")
                    self.__add_widget_property(widget, "title", child, "name", "", "attribute")
                    tabWidget.append(widget)

                    self.__add_container_fields(maplayer, widget, child, aliases)
                else:
                    tabWidget = None

                    widget = ElementTree.Element("widget")
                    widget.set("class", "QGroupBox")
                    self.__add_widget_property(widget, "title", child, "name")
                    item.append(widget)

                    self.__add_container_fields(maplayer, widget, child, aliases)
            elif child.tag == "attributeEditorField":
                tabWidget = None

                editorWidget = self.__create_editor_widget(maplayer, child.get("name"))
                if editorWidget is None:
                    continue
                editorWidget.set("name", child.get("name"))

                editorItem = ElementTree.Element("item")
                editorItem.set("row", str(row))
                editorItem.set("column", str(col + 1))
                editorItem.append(editorWidget)
                layout.append(editorItem)

                if child.get("showLabel") == "1":
                    labelItem = ElementTree.Element("item")
                    labelItem.set("row", str(row))
                    labelItem.set("column", str(col))
                    layout.append(labelItem)

                    labelWidget = ElementTree.Element("widget")
                    labelWidget.set("class", "QLabel")
                    label = aliases.get(child.get("name"), child.get("name"))
                    self.__add_widget_property(labelWidget, "text", None, None, label)
                    labelItem.append(labelWidget)

            col += 2
            if col >= 2 * ncols:
                col = 0
                row += 1

        item = ElementTree.Element("item")
        item.set("row", str(row + 1))
        item.set("column", "0")
        item.set("colspan", str(2 * ncols))
        layout.append(item)

        spacer = ElementTree.Element("spacer")
        self.__add_widget_property(spacer, "orientation", None, None, "Qt::Vertical", "property", "enum")
        item.append(spacer)
