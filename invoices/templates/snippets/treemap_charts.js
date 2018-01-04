{% for treemap in treemap_charts %}
var data = google.visualization.arrayToDataTable(
  [
  {% for item in treemap.2 %}
  {% if forloop.first %} ["{{ item.0 }}", "{{ item.1 }}", "{{ item.2 }}", "{{ item.3 }}"],
  {% else %} ["{{ item.0 }}", {% if item.1 == None %}null{% else %}"{{ item.1 }}"{% endif %}, {{ item.2|floatformat:1 }}, {{ item.3|floatformat:1 }}]{% if not forloop.last %},{% endif %}
{% endif %}{% endfor %}
  ]
)
var options = {
 title: '{{ treemap.1 }}',
 minColor: '#f00',
 midColor: '#ddd',
 maxColor: '#0d0',
 headerHeight: 15,
 fontColor: 'black',
 showScale: true,
 height: 600,
 generateTooltip: showFullTooltip
};
var chart = new google.visualization.TreeMap(document.getElementById('{{ treemap.0 }}'));
chart.draw(data, options);

{% endfor %}

function showFullTooltip(row, size, value) {
  return '<div style="background:#fd9; padding:10px; border-style:solid">' +
         '<span style="font-family:Courier"><b>' + data.getValue(row, 0) +
         '</b>, ' + data.getValue(row, 1) + ', value: ' + size +
         ', diff from past month: ' + data.getValue(row, 3) + ' </div>';
}
