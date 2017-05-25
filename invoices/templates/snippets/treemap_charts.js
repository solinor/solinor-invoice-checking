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
