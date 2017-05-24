{% for treemap in treemap_charts %}
var data = google.visualization.arrayToDataTable({{ treemap.2|safe }});
var options = {
 title: '{{ treemap.1 }}',
 minColor: '#f00',
 midColor: '#ddd',
 maxColor: '#0d0',
 headerHeight: 15,
 fontColor: 'black',
 showScale: true,
 height: 600
};
var chart = new google.visualization.TreeMap(document.getElementById('{{ treemap.0 }}'));
chart.draw(data, options);
{% endfor %}
}
