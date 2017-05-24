var dataTable = new google.visualization.DataTable();
dataTable.addColumn({ type: 'date', id: 'Date' });
dataTable.addColumn({ type: 'number', id: '{{ number_header }}' });
dataTable.addRows([
  {% for entry in entries %}[{{ entry.0 }}, {{ entry.1 }}], {% endfor %}
]);
var chart = new google.visualization.Calendar(document.getElementById('{{ destination_id }}'));
var options = {
  title: "{{ title }}",
  height: 350,
};
chart.draw(dataTable, options);
