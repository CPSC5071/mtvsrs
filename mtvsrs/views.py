import ast

import plotly.express as px
import numpy as np
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from .forms import CustomUserCreationForm
from django.views.decorators.http import require_POST
from .models import ShowTable, Movie, TvSeries, History, Watchlist, WatchlistShow


def register_user(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            success_url = reverse("login")
            return HttpResponseRedirect(success_url)
    else:
        form = CustomUserCreationForm()

    context = {"form": form}
    return render(request, "registration/registration_form.html", context)


@login_required(login_url="/login/")
def home_page(request):
    user_id = request.user.id

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
    trending_shows = get_trending_shows(request)

    context = {
        'card_count': range(10),
        'user_id': user_id,
        'new_release_shows': new_release_shows,
        'trending_shows': trending_shows
    }
    return render(request, "home.html", context)


# Create a pop up alert for no search result
@login_required(login_url="/login/")
def search_feature(request):
    if request.method == 'POST':
        search_query = request.POST.get('search_query', '')

        try:
            movie = Movie.objects.get(name__icontains=search_query)
            show_table = ShowTable.objects.get(movie_id=movie.movie_id)
            show_id = show_table.show_id
            return show_page(request, show_id)
        except Movie.DoesNotExist:
            pass

        try:
            tv_series = TvSeries.objects.get(name__icontains=search_query)
            show_table = ShowTable.objects.get(tv_series_id=tv_series.tv_series_id)
            show_id = show_table.show_id
            return show_page(request, show_id)
        except TvSeries.DoesNotExist:
            context = {'error_message': 'No search result, please check again'}
    return render(request, 'post_search.html', context)


@login_required(login_url="/login/")
def show_page(request, show_id):
    user_id = request.user.id
    watchlist_id = Watchlist.objects.get(user_id=user_id).watchlist_id
    try:
        current_status = WatchlistShow.objects.get(watchlist_id=watchlist_id, show_id=show_id).status
    except WatchlistShow.DoesNotExist:
        current_status = None

    ### Show data ###
    show = get_object_or_404(ShowTable, pk=show_id)
    if show.movie_id:
        show = get_object_or_404(Movie, pk=show.movie_id)
        show_type = "Movie"
    else:
        show = get_object_or_404(TvSeries, pk=show.tv_series_id)
        show_type = "TV"
    # parse genre string into list, then concat them with just a comma
    literal_eval_genre = ast.literal_eval(show.genre)
    show.genre = ', '.join(literal_eval_genre)

    ### Similar shows ##
    show_genres_set = set(literal_eval_genre)
    movies = Movie.objects.all()
    tv_shows = TvSeries.objects.all()
    movies_common = [movie for movie in movies if len(set(ast.literal_eval(movie.genre)) & show_genres_set) >= 2][:5]
    tv_shows_common = [tv_show for tv_show in tv_shows if
                       len(set(ast.literal_eval(tv_show.genre)) & show_genres_set) >= 2][:5]
    similar_shows = movies_common + tv_shows_common
    similar_shows = sorted(similar_shows, key=lambda x: x.release_date)

    ### Reviews ###
    review_count = History.objects.filter(show_id=show_id).count()
    reviews = History.objects.filter(show_id=show_id).select_related('user_id').order_by('-review_date')[:5]

    ### Status distribution ###
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

    ### Score distribution ###
    score_distribution_query = """
        SELECT rating FROM History WHERE Show_ID = %s;
    """
    # initialize for histogram, technically not necessary and we can use px.histogram
    # but because our data is sparse sometimes there are no counts for a rating
    score_distribution = {score: 0 for score in np.arange(1, 6)}

    ### Execute queries ###
    with (connection.cursor() as cursor):
        ### Status distribution ###
        cursor.execute(status_distribution_query, [show_id])
        for row in cursor.fetchall():
            status_distribution[row[0]] = row[1]

        ### Score distribution ###
        cursor.execute(score_distribution_query, [show_id])
        for row in cursor.fetchall():
            score_distribution[row[0]] += 1

    ### Score distribution ###
    ratings = list(score_distribution.keys())
    counts = list(score_distribution.values())
    score_distribution_plot = px.bar(
        x=ratings,
        y=counts,
        color=counts,
        color_continuous_scale=[(0, "red"), (0.5, "yellow"), (1, "green")]
    )
    # remove all labels and make responsive
    score_distribution_plot.update_layout(
        xaxis_title="",
        yaxis_title="",
        title="",
        xaxis_showticklabels=True,
        yaxis_showticklabels=False,
        xaxis_visible=True,
        yaxis_visible=False,
        autosize=True,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",  # transparent background
        coloraxis_showscale=False,  # hide the color scale bar
        hovermode=False,
        bargap=0.4
    )
    # adjust marker properties
    score_distribution_plot.update_traces(
        marker_line_width=0,  # borders around bars
        marker_opacity=0.6,
    )
    score_distribution_plot = score_distribution_plot.to_html(full_html=False, config={'displayModeBar': False})

    ### Build context and return ###
    context = {
        'show': show,  # this will not have show_id, but movie_id or tv_series_id
        'show_id': show_id,
        'show_type': show_type,
        'watchlist_id': watchlist_id,
        'current_status': current_status,
        'status_types': status_types,
        'status_distribution': status_distribution,
        'score_distribution_plot': score_distribution_plot,
        'review_count': review_count,
        'reviews': reviews,
        'card_count': range(10),
        'user_id': user_id,
        'similar_shows': similar_shows
    }

    return render(request, "show.html", context)


@login_required(login_url="/login/")
def my_list_page(request):
    user_id = request.user.id
    watchlist_id = Watchlist.objects.get(user_id=user_id).watchlist_id
    watchlist_show = WatchlistShow.objects.filter(watchlist_id=watchlist_id).select_related('show_id')

    shows = []
    for show in watchlist_show:
        if show.show_id.movie_id:
            show = get_object_or_404(Movie, pk=show.show_id.movie_id)
            show.type = "Movie"
        else:
            show = get_object_or_404(TvSeries, pk=show.show_id.tv_series_id)
            show.type = "TV"
        show.genre = ', '.join(ast.literal_eval(show.genre))
        shows.append(show)

    context = {
        'shows': shows,
        'card_count': range(10),
        'user_id': user_id
    }
    return render(request, "my_list.html", context)


def get_trending_shows(request):
    top_histories = History.objects.filter(rating=5).order_by('-review_date')[:10]
    trending_shows = []

    for history in top_histories:
        try:
            show = history.show_id

            if show.movie_id is not None:
                movie = Movie.objects.get(movie_id=show.movie_id)
                trending_shows.append({'name': movie.name, 'description': movie.description})

            elif show.tv_series_id is not None:
                series = TvSeries.objects.get(tv_series_id=show.tv_series_id)
                trending_shows.append({'name': series.name, 'description': series.description})

        except ShowTable.DoesNotExist:
            pass

    return trending_shows


@require_POST
def change_status(request):
    watchlist_id = int(request.POST.get('watchlistId'))
    show_id = int(request.POST.get('showId'))
    new_status = request.POST.get('newStatus')

    # these 2 below are poorly error handled, but no time, though by this point they should exist
    watchlist = Watchlist.objects.get(watchlist_id=watchlist_id)
    show = ShowTable.objects.get(show_id=show_id)

    # although watchlistshow takes in id, somehow it insists on taking in the object, maybe django's way to force integriy
    watchlist_show, created = WatchlistShow.objects.get_or_create(
        watchlist_id=watchlist,
        show_id=show,
        defaults={'status': new_status, 'added_date': date.today()}
    )

    # update the status if the object was found rather than created
    if not created:
        watchlist_show.status = new_status
        watchlist_show.save(update_fields=["status"])

    return HttpResponse(f'<span id="statusLabel">{new_status}</span>')
