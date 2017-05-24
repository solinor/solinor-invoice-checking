{% for calendar_chart in calendar_charts %}
{% include "snippets/calendar_chart.js" with number_header=calendar_chart.2 entries=calendar_chart.3 destination_id=calendar_chart.0 title=calendar_chart.1 %}
{% endfor %}
