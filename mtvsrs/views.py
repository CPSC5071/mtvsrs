from django.shortcuts import render, get_object_or_404
from django.db import connection
from .models import ShowTable, Movie, TvSeries
from django.contrib.auth.decorators import login_required


# @login_required()
def home_page(request):
    # Using raw queries as syntax for Django ORM is new to me
    new_release_columns = ['Show_ID', 'Show_Name', 'Show_Description', 'Show_Type']
    new_release_query = """
        SELECT 
            st.Show_ID as Show_ID,
            unioned.Show_Name as Show_Name,
            unioned.Show_Description as Show_Description,
            unioned.Show_Type as Show_Type,
            unioned.Show_Release_Date as Show_Release_Date
        FROM
            (
                (SELECT
                    Movie_ID AS Show_ID,
                    Name AS Show_Name,
                    Description as Show_Description,
                    'Movie' AS Show_Type,
                    Release_Date AS Show_Release_Date
                FROM
                    Movie)

                UNION ALL

                (SELECT
                    TV_Series_ID AS Show_ID,
                    Name AS Show_Name,
                    Description as Show_Description,
                    'TV' AS Show_Type,
                    Release_Date AS Show_Release_Date
                FROM
                    TV_Series)
            ) AS unioned
        JOIN
            Show_Table st ON 
            (st.Movie_ID = unioned.Show_ID)
            OR 
            (st.TV_Series_ID = unioned.Show_ID)
        ORDER BY 
            Show_Release_Date DESC 
        LIMIT 10;
    """

    with connection.cursor() as cursor:
        cursor.execute(new_release_query)
        new_release_shows = cursor.fetchall()
        new_release_shows = [
            # exclude release date
            {new_release_columns[i]: value for i, value in enumerate(show[:-1])} for show in new_release_shows
        ]

    context = {
        'card_count': range(10),
        'new_release_shows': new_release_shows
    }
    return render(request, "home.html", context)


def show_page(request, show_id):
    show = get_object_or_404(ShowTable, pk=show_id)

    if show.movie_id:
        show_type = "Movie"
        show = get_object_or_404(Movie, pk=show.movie_id)
    else:
        show_type = "TV",
        show = get_object_or_404(TvSeries, pk=show.tv_series_id)

    context = {
        'show': show,
        'show_type': show_type
    }

    return render(request, "show.html", context)