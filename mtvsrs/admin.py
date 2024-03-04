from django.contrib import admin
from .models import Movie, TvSeries, ShowTable

class MovieAdmin(admin.ModelAdmin):
    list_display = ("movie_id", "name", 'description', 'genre', 'release_date')
admin.site.register(Movie, MovieAdmin)

class TvSeriesAdmin(admin.ModelAdmin):
    list_display = ("tv_series_id", "name", 'description', 'genre', 'release_date')
admin.site.register(TvSeries, TvSeriesAdmin)

class ShowTableAdmin(admin.ModelAdmin):
    list_display = ("show_id", "tv_series_id", "movie_id")
admin.site.register(ShowTable, ShowTableAdmin)