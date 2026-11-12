import json

import mwparserfromhell


def analyse_json(page_text):
    try:
        parsed_data = json.loads(page_text)

    except json.JSONDecodeError:
        return {
            "is_valid_json": False,
            "json_data_type": None,
            "json_entry_count": None,
        }

    data_type = type(parsed_data).__name__

    if isinstance(parsed_data, (dict, list)):
        entry_count = len(parsed_data)
    else:
        entry_count = None

    return {
        "is_valid_json": True,
        "json_data_type": data_type,
        "json_entry_count": entry_count,
    }


def analyse_wiki_markup(page_text):
    wikicode = mwparserfromhell.parse(page_text)

    templates = wikicode.filter_templates()
    template_names = {}

    for template in templates:
        template_name = str(template.name).strip()

        if template_name not in template_names:
            template_names[template_name] = 0

        template_names[template_name] += 1

    links = wikicode.filter_wikilinks()
    link_destinations = {}
    link_details = []

    for link in links:
        destination = str(link.title).strip()
        display_text = str(link.text).strip() if link.text is not None else destination

        link_details.append(
            {
                "destination": destination,
                "display_text": display_text,
            }
        )

        if destination not in link_destinations:
            link_destinations[destination] = 0

        link_destinations[destination] += 1

    external_links = wikicode.filter_external_links()
    headings = wikicode.filter_headings()
    tags = wikicode.filter_tags()

    tag_names = {}

    for tag in tags:
        tag_name = str(tag.tag).lower()

        if tag_name not in tag_names:
            tag_names[tag_name] = 0

        tag_names[tag_name] += 1

    return {
        "template_count": len(templates),
        "template_names": template_names,
        "wikilink_count": len(links),
        "link_destinations": link_destinations,
        "external_link_count": len(external_links),
        "heading_count": len(headings),
        "tag_count": len(tags),
        "tag_names": tag_names,
        "link_details": link_details,
    }


def analyse_content_structure(page_text):
    json_results = analyse_json(page_text)
    wiki_results = analyse_wiki_markup(page_text)

    return {
        **json_results,
        **wiki_results,
    }


def analyse_template_relationships(page_text):
    wikicode = mwparserfromhell.parse(page_text)

    relationships = {}

    def inspect_templates(templates, parent_name=None):
        for template in templates:
            template_name = str(template.name).strip()

            if parent_name is not None:
                if parent_name not in relationships:
                    relationships[parent_name] = {}

                if template_name not in relationships[parent_name]:
                    relationships[parent_name][template_name] = 0

                relationships[parent_name][template_name] += 1

            for parameter in template.params:
                nested_templates = parameter.value.filter_templates()

                inspect_templates(nested_templates, template_name)

    inspect_templates(wikicode.filter_templates())

    return relationships


def analyse_template_parameters(page_text):
    wikicode = mwparserfromhell.parse(page_text)

    parameter_counts = {}

    for template in wikicode.filter_templates():
        template_name = str(template.name).strip()

        if template_name not in parameter_counts:
            parameter_counts[template_name] = {}

        for parameter in template.params:
            parameter_name = str(parameter.name).strip()

            if parameter_name not in parameter_counts[template_name]:
                parameter_counts[template_name][parameter_name] = 0

            parameter_counts[template_name][parameter_name] += 1

    return parameter_counts
