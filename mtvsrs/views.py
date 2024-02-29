from django.shortcuts import render
from django.db import connection
from django.contrib.auth.decorators import login_required


# @login_required()
def home(request):
    new_release_columns = ['Show_ID', 'Show_Name', 'Show_Description', 'Type']
    new_release_query = """
    (SELECT
        Movie_ID AS Show_ID,
        Name AS Show_Name,
        Description as Show_Description,
        'Movie' AS Type,
        Release_Date AS Show_Release_Date
    FROM
        Movie)

    UNION ALL

    (SELECT
        TV_Series_ID AS Show_ID,
        Name AS Show_Name,
        Description as Show_Description,
        'TV' AS Type,
        Release_Date AS Show_Release_Date

    FROM
        TV_Series)


    ORDER BY Show_Release_Date DESC
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

