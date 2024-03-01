from django.shortcuts import render, redirect
from mtvsrs.models import Movie
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render, redirect

def register_user(request: HttpRequest) -> HttpResponse:

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            success_url = reverse("index")
            return HttpResponseRedirect(success_url)
    else:
        form = UserCreationForm()

    context = {"form": form}

    return render(request, "registration/registration_form.html", context)
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

def search_feature(request):
    # Check if the request is a post request.
    if request.method == 'POST':
        # Retrieve the search query entered by the user
        search_query = request.POST['search_query']
        # Filter your model by the search query
        posts = Movie.objects.filter(name__contains=search_query)
        return render(request, 'post_search.html', {'query':search_query, 'posts':posts})
    else:
        return render(request, 'post_search.html',{})




def show_page(request, show_id):
    show = get_object_or_404(ShowTable, pk=show_id)

    if show.movie_id:
        show = get_object_or_404(Movie, pk=show.movie_id)
        show_type = "Movie"

    else:
        show = get_object_or_404(TvSeries, pk=show.tv_series_id)
        show_type = "TV"

    status_types = ['Planned', 'Watching', 'Completed', 'Dropped']

    # pass in show_id as parameter when executing query rather than string interpolation to prevent sql injection
    status_distribution_query = """
        SELECT
            Status, COUNT(*) as Count
        FROM
            WatchlistShow
        WHERE
            Show_ID = %s
        GROUP BY Status;
    """

   # if status is not in the query results, count should be 0, so init an empty dict first
    status_distribution = {status_type: 0 for status_type in status_types}

    with connection.cursor() as cursor:
        cursor.execute(status_distribution_query, [show_id])
        for row in cursor.fetchall():
            status_distribution[row[0]] = row[1]

    context = {
        'show': show,
        'show_type': show_type,
        'status_distribution': status_distribution
    }

    return render(request, "show.html", context)